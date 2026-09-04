from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.db.models import F, ExpressionWrapper, DecimalField, Q
from django.db import transaction
from django.db.models.functions import NullIf
from .model_views import PortfolioSummary
from .models import Price
from django.db.models import OuterRef, Subquery
from .models import WatchlistEntry, Watchlist, Asset, Holdings, NewsEvent, FiftyTwoWeekRange, FondHolding, ManualFondHolding, FinConfig, NameAlias, PriceAlarm, PriceAlarmEvent, format_price_alarm_message, TrailingStopLoss, TrailingStopEvent, format_trailing_stop_message, NewsArticle
from telegram_app.libs.telegram_api import send_telegram_message
from .models_helper.category_class import CategoryClass
from .models_helper.asset_class import AssetClass
from django.utils.text import slugify
from django.http import Http404
from .apis.services.openfigi import OpenFigiService
import asyncio
import json
import csv
import io
import zipfile
from decimal import Decimal, InvalidOperation
from typing import Tuple

from asgiref.sync import async_to_sync, sync_to_async
from .apis.services.csv_import import import_transactions
from django.contrib import messages
from django.core.management import call_command
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .services import resolve_asset_with_price, refresh_asset_price, report_price_fetch_failures, compute_stock_lookthrough_rows

import logging

logger = logging.getLogger(__name__)

def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def _is_api_key_valid(request) -> bool:
    api_key = getattr(settings, "FINTECH_API_KEY", None)
    if not api_key:
        return False
    return request.headers.get("X-Api-Key", "") == api_key

def _enrich_symbols(rows: list) -> None:
    """
    Füllt Asset.symbol für alle Rows, die noch kein Symbol haben, via OpenFIGI nach.
    Das Symbol wird normalisiert gespeichert (TradingView-URL-Format, z.B. "HKEX-9880").
    Max. 5 neue Lookups pro Seitenaufruf, um die OpenFIGI-API nicht zu überlasten.
    """
    from .apis.services.openfigi import OpenFigiService

    missing = [r for r in rows if not r.get('symbol')]
    if not missing:
        return

    svc = OpenFigiService()
    fetched = 0
    max_per_request = 5

    for row in missing:
        if fetched >= max_per_request:
            break
        isin = row['isin']
        try:
            symbol = svc.isin2symbol(isin)
            if symbol:
                tv_symbol = symbol.replace(':', '-').replace('.', '-')
                Asset.objects.filter(pk=row['asset_id']).update(symbol=tv_symbol)
                row['symbol'] = tv_symbol
                logger.info(f"Symbol auto-fetched for {isin}: {symbol} → {tv_symbol}")
                fetched += 1
        except Exception as exc:
            logger.warning(f"Symbol lookup failed for {isin}: {exc}")


from .libs.currency_utils import to_eur as _to_eur


def _enrich_week52(rows: list) -> None:
    """
    Ergänzt jede Row um week52_high, week52_low, pct_from_high, pct_from_low.
    Alle Werte werden in EUR gespeichert und verglichen.
    Holt fehlende oder abgelaufene Einträge live von Yahoo Finance und speichert sie.
    Fehler pro Asset werden still als None gesetzt (Seite bleibt nutzbar).
    """
    from .apis.services.yahoo_finance import YahooFinanceRequest
    from .apis.services.comdirect_finance import ComdirectFinanceRequest

    asset_ids = [r['asset_id'] for r in rows]
    existing = {
        r.asset_id: r
        for r in FiftyTwoWeekRange.objects.filter(asset_id__in=asset_ids)
    }

    yahoo     = YahooFinanceRequest()
    comdirect = ComdirectFinanceRequest()

    for row in rows:
        aid  = row['asset_id']
        isin = row['isin']
        rng  = existing.get(aid)

        # Blacklist-Eintrag: nie löschen, nie neu holen — aber vorhandene Werte anzeigen
        if rng and rng.skip_yahoo:
            # Prozentberechnung mit manuell eingetragenen Werten (falls vorhanden)
            if rng.week52_high and rng.week52_low:
                try:
                    cur = row.get('current_price')
                    if cur:
                        row['week52_high']   = rng.week52_high
                        row['week52_low']    = rng.week52_low
                        row['pct_from_high'] = (Decimal(str(cur)) / rng.week52_high - 1) * 100
                        row['pct_from_low']  = (Decimal(str(cur)) / rng.week52_low  - 1) * 100
                    else:
                        row['week52_high'] = rng.week52_high
                        row['week52_low']  = rng.week52_low
                        row['pct_from_high'] = row['pct_from_low'] = None
                except Exception:
                    row['week52_high'] = row['week52_low'] = row['pct_from_high'] = row['pct_from_low'] = None
            else:
                row['week52_high'] = row['week52_low'] = row['pct_from_high'] = row['pct_from_low'] = None
            continue

        # Abgelaufen → löschen und neu holen
        if rng and rng.is_expired():
            rng.delete()
            rng = None

        # Fehlend → von Yahoo holen, bei Fehler Comdirect als Fallback
        if rng is None:
            data     = None
            provider = None

            try:
                data     = yahoo.isin2week52(isin)
                provider = 'yahoo'
            except Exception as exc:
                logger.warning(f"Yahoo 52W failed for {isin}: {exc} — trying Comdirect")

            if data is None:
                try:
                    data     = comdirect.isin2week52(isin)
                    provider = 'comdirect'
                except Exception as exc:
                    logger.warning(f"Comdirect 52W failed for {isin}: {exc}")

            if data is not None:
                try:
                    currency = data.get('currency', 'EUR')
                    high_eur = _to_eur(data['high'], currency)
                    low_eur  = _to_eur(data['low'],  currency)
                    rng = FiftyTwoWeekRange.objects.create(
                        asset_id=aid,
                        week52_high=high_eur,
                        week52_high_date=None,
                        week52_low=low_eur,
                        week52_low_date=None,
                        fetched_at=timezone.now(),
                    )
                    logger.info(f"52W stored for {isin} via {provider}: H={high_eur} L={low_eur} EUR (orig {currency})")
                except Exception as exc:
                    logger.warning(f"52W DB save failed for {isin}: {exc}")
                    rng = None

        # Prozentuale Abweichungen berechnen — alles in EUR, current_price aus Asset
        if rng:
            try:
                cur = row.get('current_price')  # EUR aus Asset-Tabelle
                if cur and rng.week52_high and rng.week52_low:
                    row['week52_high']   = rng.week52_high
                    row['week52_low']    = rng.week52_low
                    row['pct_from_high'] = (Decimal(str(cur)) / rng.week52_high - 1) * 100
                    row['pct_from_low']  = (Decimal(str(cur)) / rng.week52_low  - 1) * 100
                else:
                    row['week52_high'] = row['week52_low'] = row['pct_from_high'] = row['pct_from_low'] = None
            except Exception:
                row['week52_high'] = row['week52_low'] = row['pct_from_high'] = row['pct_from_low'] = None
        else:
            row['week52_high'] = row['week52_low'] = row['pct_from_high'] = row['pct_from_low'] = None


@login_required
def portfolio_overall(request):
    """Alle Holdings, sortiert nach Gesamtperformance. Inkl. CSV-Export."""
    import csv
    from django.http import HttpResponse

    today = timezone.now().date()
    yesterday_sq = Price.objects.filter(
        asset=OuterRef('asset_id'),
        timestamp__date__lt=today,
    ).order_by('-timestamp').values('current_price')[:1]

    holdings = (
        Holdings.objects
        .select_related('asset')
        .filter(category__gte=20, quantity__gt=0)
        .annotate(yesterday_price=Subquery(
            yesterday_sq, output_field=DecimalField(max_digits=20, decimal_places=4)
        ))
        .order_by('asset__name')
    )

    rows = []
    for h in holdings:
        invested   = (h.average_purchase_price or Decimal('0')) * h.quantity
        cur_price  = h.asset.current_price or Decimal('0')
        yest_price = getattr(h, 'yesterday_price', None) or Decimal('0')
        current    = cur_price  * h.quantity
        yesterday  = yest_price * h.quantity

        simple   = (current / invested  - 1) * 100 if invested  > 0 else None
        gain_abs = current - invested              if invested  > 0 else None
        day_perc = (current / yesterday - 1) * 100 if yesterday > 0 else None
        day_abs  = current - yesterday             if yesterday > 0 else None

        cat_label = CategoryClass(h.category).label if h.category else '–'

        rows.append({
            'holdings_id':    h.pk,
            'asset_id':       h.asset.pk,
            'name':           h.asset.name,
            'isin':           h.asset.isin,
            'symbol':         h.asset.symbol or '',
            'logo':           h.asset.logo or '',
            'asset_class':    h.asset.asset_class,
            'category':       cat_label,
            'quantity':       h.quantity,
            'avg_price':      h.average_purchase_price,
            'current_price':  h.asset.current_price,
            'yesterday_price': yest_price if yest_price else None,
            'invested':       invested,
            'current':        current,
            'gain_abs':       gain_abs,
            'simple':         simple,
            'day_perc':       day_perc,
            'day_abs':        day_abs,
            'not_for_sale':   h.not_for_sale,
            'stake_recovered': h.stake_recovered,
        })

    # ── Fehlende Symbole via OpenFIGI nachfüllen ─────────────────────────────
    _enrich_symbols(rows)

    # ── 52-Wochen-Range: prüfen / nachladen / berechnen ──────────────────────
    _enrich_week52(rows)

    # CSV-Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="portfolio_overall.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Name', 'ISIN', 'Kategorie', 'Asset Class', 'Menge',
                         'Einstand €', 'Aktuell €', 'Investiert €', 'Wert €',
                         'G/V €', 'G/V %', 'Tag €', 'Tag %',
                         '52W-Hoch', '52W-Tief', 'Abst. 52W-H %', 'Abst. 52W-T %'])
        for r in sorted(rows, key=lambda x: x['simple'] if x['simple'] else Decimal('-999'), reverse=True):
            writer.writerow([
                r['name'], r['isin'], r['category'], r['asset_class'],
                str(r['quantity']).replace('.', ','),
                str(r['avg_price'] or '').replace('.', ','),
                str(r['current_price'] or '').replace('.', ','),
                str(r['invested']).replace('.', ','),
                str(r['current']).replace('.', ','),
                str(r['gain_abs'] or '').replace('.', ','),
                f"{r['simple']:.2f}".replace('.', ',') if r['simple'] is not None else '',
                str(r['day_abs'] or '').replace('.', ','),
                f"{r['day_perc']:.2f}".replace('.', ',') if r['day_perc'] is not None else '',
                str(r.get('week52_high') or '').replace('.', ','),
                str(r.get('week52_low') or '').replace('.', ','),
                f"{r['pct_from_high']:.2f}".replace('.', ',') if r.get('pct_from_high') is not None else '',
                f"{r['pct_from_low']:.2f}".replace('.', ',') if r.get('pct_from_low') is not None else '',
            ])
        return response

    rows.sort(key=lambda r: r['simple'] if r['simple'] is not None else Decimal('-999'), reverse=True)

    total_inv  = sum(r['invested'] for r in rows)
    total_cur  = sum(r['current']  for r in rows)
    total_yest = sum(r['current'] - r['day_abs'] for r in rows if r['day_abs'] is not None)

    day_total_abs = total_cur - total_yest if total_yest else None
    day_total_pct = (total_cur / total_yest - 1) * 100 if total_yest else None

    return render(request, 'fintech/portfolio_overall.html', {
        'rows':          rows,
        'total_inv':     total_inv,
        'total_cur':     total_cur,
        'total_yest':    total_yest,
        'gain_total':    total_cur - total_inv,
        'simple_total':  (total_cur / total_inv - 1) * 100 if total_inv else None,
        'day_total_abs': day_total_abs,
        'day_total_pct': day_total_pct,
    })


def portfolio_overall_stocks(request):
    """
    Aktien-Look-Through-Übersicht: eine Zeile pro Aktie (direkt gehalten
    und/oder über Fonds/ETFs gehalten via FondHolding-Mapping), mit direktem
    + über Fonds gehaltenem Anteil. Berechnung siehe
    services.compute_stock_lookthrough_rows (auch von update_news genutzt).
    """
    rows = compute_stock_lookthrough_rows()

    total_stock = sum(r['value_stock'] for r in rows) if rows else Decimal('0')
    total_fund  = sum(r['value_fund']  for r in rows) if rows else Decimal('0')

    return render(request, 'fintech/portfolio_overall_stocks.html', {
        'rows':        rows,
        'total_stock': total_stock,
        'total_fund':  total_fund,
        'total_all':   total_stock + total_fund,
    })


@staff_member_required
def test_api(request):
    return render(request, 'fintech/test_api.html')


@staff_member_required
def test_api_lookup(request):
    """AJAX: ISIN → Asset-Name aus DB."""
    isin = request.GET.get('isin', '').strip().upper()
    if not isin:
        return JsonResponse({'name': None})
    asset = Asset.objects.filter(isin=isin).first()
    return JsonResponse({
        'name': asset.name if asset else None,
        'asset_class': asset.asset_class if asset else None,
    })


@staff_member_required
def test_api_run(request):
    """AJAX: führt eine API-Aktion aus und gibt Ergebnisse aller Provider zurück."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    import json as _json
    body = _json.loads(request.body)
    isin   = body.get('isin', '').strip().upper()
    action = body.get('action', '')

    if not isin:
        return JsonResponse({'error': 'ISIN fehlt'}, status=400)

    from .apis.services.provider_manager import ProviderManager
    from .apis.services.openfigi import OpenFigiService
    from .apis.services.request_lib import KeyNotFoundWarning, KeyNotFoundError
    from .models_helper.asset_class import AssetClass

    pm  = ProviderManager()
    results = []

    if action == 'price':
        from .apis.services.exchange_rate_proxy import CurrencyProxy
        from .libs.general.converter import string2dec
        fx = CurrencyProxy()

        def to_eur(price_str, currency):
            """Gibt (eur_price, fx_rate, fx_source) zurück."""
            try:
                dec = string2dec(price_str)
                if currency == 'EUR':
                    return str(round(dec, 4)), '1,0000', '–'
                rate = fx.get_rate(currency)
                eur  = round(dec / rate, 4)
                return str(eur), str(round(rate, 4)), 'Frankfurter API'
            except Exception as e:
                return 'n/a', 'n/a', str(e)

        def add_price_result(provider, price, currency):
            eur, fx_rate, fx_src = to_eur(price, currency)
            results.append({
                'provider': provider,
                'price':    f'{price}',
                'currency': currency,
                'fx_rate':  fx_rate if currency != 'EUR' else '–',
                'fx_src':   fx_src  if currency != 'EUR' else '–',
                'eur':      eur,
                'ok':       True,
            })

        # Comdirect — alle Asset-Klassen
        for ac_value, ac_label in AssetClass.choices:
            try:
                price, currency = pm.com_requester[ac_value].isin2price(isin)
                add_price_result(f'Comdirect ({ac_label})', price, currency)
            except (KeyNotFoundWarning, KeyNotFoundError):
                results.append({'provider': f'Comdirect ({ac_label})', 'ok': False})
            except Exception as e:
                results.append({'provider': f'Comdirect ({ac_label})', 'ok': False, 'error': str(e)})

        # Yahoo Finance
        try:
            price, currency = pm.yahoo_request.isin2price(isin)
            add_price_result('Yahoo Finance', price, currency)
        except Exception:
            results.append({'provider': 'Yahoo Finance', 'ok': False})

        # AlleAktien
        try:
            _, price, currency, _ = pm.alle_aktien_request.get_infos(isin)
            add_price_result('AlleAktien', price, currency)
        except Exception:
            results.append({'provider': 'AlleAktien', 'ok': False})

        # JustETF
        try:
            price, currency = pm.just_etf_request.isin2price(isin)
            add_price_result('JustETF', price, currency)
        except Exception:
            results.append({'provider': 'JustETF', 'ok': False})

    elif action == 'symbol':
        svc = OpenFigiService()
        # Rohkandidaten aus OpenFIGI anzeigen
        try:
            candidates = svc._query([isin])
            all_cands = candidates[0] if candidates else []
            if all_cands:
                for c in all_cands[:8]:
                    ticker = c.get('ticker', '–')
                    exch   = c.get('exchCode', '–')
                    sector = c.get('marketSector', '–')
                    built  = svc._build(c) or 'n/a'
                    results.append({
                        'provider': f'OpenFIGI ({exch} / {sector})',
                        'value': f'{built}  [ticker={ticker}]',
                        'ok': bool(svc._build(c)),
                    })
                # Gewähltes Symbol
                best = svc._best_symbol(isin, all_cands)
                results.append({
                    'provider': '→ Gewähltes Symbol',
                    'value': best or 'n/a',
                    'ok': bool(best),
                })
                # In Asset.symbol speichern — normalisiert für TradingView-URLs:
                # "HKEX:9880" → "HKEX-9880",  "9880.HK" → "9880-HK"
                if best:
                    tv_symbol = best.replace(':', '-').replace('.', '-')
                    asset = Asset.objects.filter(isin=isin).first()
                    if asset:
                        old_symbol = asset.symbol or ''
                        asset.symbol = tv_symbol
                        asset.save(update_fields=['symbol'])
                        label = f'{old_symbol} → {tv_symbol}' if (old_symbol and old_symbol != tv_symbol) else tv_symbol
                        results.append({'provider': '✅ Asset.symbol gespeichert',
                                        'value': label, 'ok': True})
            else:
                results.append({'provider': 'OpenFIGI', 'value': 'n/a', 'ok': False})
        except Exception as e:
            results.append({'provider': 'OpenFIGI', 'value': f'Fehler: {e}', 'ok': False})

    elif action == 'wkn':
        # Comdirect
        for ac_value, ac_label in AssetClass.choices:
            try:
                wkn = pm.com_requester[ac_value].isin2wkn(isin)
                results.append({'provider': f'Comdirect ({ac_label})', 'value': wkn, 'ok': True})
            except (KeyNotFoundWarning, KeyNotFoundError):
                results.append({'provider': f'Comdirect ({ac_label})', 'value': 'n/a', 'ok': False})
            except Exception as e:
                results.append({'provider': f'Comdirect ({ac_label})', 'value': f'Fehler: {e}', 'ok': False})

        # JustETF
        try:
            wkn = pm.just_etf_request.isin2wkn(isin)
            results.append({'provider': 'JustETF', 'value': wkn, 'ok': True})
        except Exception:
            results.append({'provider': 'JustETF', 'value': 'n/a', 'ok': False})

        # AlleAktien
        try:
            wkn = pm.alle_aktien_request.isin2wkn(isin)
            results.append({'provider': 'AlleAktien', 'value': wkn, 'ok': True})
        except Exception:
            results.append({'provider': 'AlleAktien', 'value': 'n/a', 'ok': False})

    elif action == 'week52':
        from .apis.services.yahoo_finance import YahooFinanceRequest
        from .apis.services.comdirect_finance import ComdirectFinanceRequest
        from .models import FiftyTwoWeekRange

        save_to_db = body.get('save_to_db', False)
        asset = Asset.objects.filter(isin=isin).first()

        def _week52_row(provider, data, source='live'):
            currency = data.get('currency', '?')
            try:
                high_eur = _to_eur(data['high'], currency)
                low_eur  = _to_eur(data['low'],  currency)
            except Exception as e:
                return {'provider': provider, 'ok': False, 'error': f'EUR-Umrechnung: {e}'}
            return {
                'provider': provider, 'ok': True,
                'high': f"{high_eur:.4f}", 'low': f"{low_eur:.4f}",
                'cur': '–', 'currency': 'EUR',
                'pct_high': '–', 'pct_low': '–',
                'source': f'{source} (orig {currency})',
            }

        # Yahoo Finance
        yahoo_data = None
        try:
            yahoo_data = YahooFinanceRequest().isin2week52(isin)
            results.append(_week52_row('Yahoo Finance', yahoo_data))
        except Exception as e:
            results.append({'provider': 'Yahoo Finance', 'ok': False, 'error': str(e)})

        # Comdirect
        comdirect_data = None
        try:
            comdirect_data = ComdirectFinanceRequest().isin2week52(isin)
            results.append(_week52_row('Comdirect', comdirect_data))
        except Exception as e:
            results.append({'provider': 'Comdirect', 'ok': False, 'error': str(e)})

        # In DB speichern (erster erfolgreicher Provider), wenn gewünscht oder kein Eintrag vorhanden
        best_data = yahoo_data or comdirect_data
        if best_data and asset:
            existing_rng = None
            try:
                existing_rng = asset.week52
            except FiftyTwoWeekRange.DoesNotExist:
                pass

            should_save = save_to_db or (existing_rng is None) or existing_rng.is_expired()
            if should_save:
                try:
                    if existing_rng:
                        existing_rng.delete()
                    currency = best_data.get('currency', 'EUR')
                    FiftyTwoWeekRange.objects.create(
                        asset=asset,
                        week52_high=_to_eur(best_data['high'], currency),
                        week52_high_date=None,
                        week52_low=_to_eur(best_data['low'], currency),
                        week52_low_date=None,
                        fetched_at=timezone.now(),
                    )
                    provider_used = 'Yahoo Finance' if yahoo_data else 'Comdirect'
                    results.append({'provider': '✅ In DB gespeichert (EUR)', 'ok': True,
                                    'high': '–', 'low': '–', 'cur': '–', 'currency': 'EUR',
                                    'pct_high': '–', 'pct_low': '–',
                                    'source': f'via {provider_used}'})
                except Exception as e:
                    results.append({'provider': '❌ DB-Speichern fehlgeschlagen', 'ok': False, 'error': str(e)})

        # DB-Cache anzeigen
        if asset:
            try:
                r = asset.week52
                cur_f  = float(asset.current_price) if asset.current_price else None
                high_f = float(r.week52_high)
                low_f  = float(r.week52_low)
                pct_h = (cur_f / high_f - 1) * 100 if (cur_f and high_f) else None
                pct_l = (cur_f / low_f  - 1) * 100 if (cur_f and low_f)  else None
                expired_flag = ' ⚠ abgelaufen' if r.is_expired() else ''
                results.append({
                    'provider': f'DB-Cache{expired_flag}',
                    'ok': not r.is_expired(),
                    'high': f"{high_f:.4f}", 'low': f"{low_f:.4f}",
                    'cur':  f"{cur_f:.4f}" if cur_f else '–',
                    'currency': 'EUR',
                    'pct_high': f"{pct_h:+.1f} %" if pct_h is not None else '–',
                    'pct_low':  f"{pct_l:+.1f} %" if pct_l is not None else '–',
                    'source': f"DB ({r.fetched_at.strftime('%d.%m.%Y %H:%M')})",
                })
            except FiftyTwoWeekRange.DoesNotExist:
                results.append({'provider': 'DB-Cache', 'ok': False, 'error': 'Kein Eintrag in DB'})
        else:
            results.append({'provider': 'DB-Cache', 'ok': False, 'error': 'ISIN nicht in Assets-DB'})

    else:
        return JsonResponse({'error': f'Unbekannte Aktion: {action}'}, status=400)

    return JsonResponse({'results': results})


@login_required
def fintech_index(request):
    return render(request, 'fintech/index.html')


@staff_member_required
def trigger_update_prices(request):
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    try:
        call_command('update_prices')
        messages.success(request, 'Kurs-Update erfolgreich abgeschlossen.')
    except Exception as e:
        messages.error(request, f'Fehler beim Kurs-Update: {e}')
    return redirect('fintech:fintech-index')


@staff_member_required
def trigger_update_etf_holdings(request):
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    try:
        call_command('update_etf_holdings')
        messages.success(request, 'ETF-Holdings-Update erfolgreich abgeschlossen.')
    except Exception as e:
        messages.error(request, f'Fehler beim ETF-Holdings-Update: {e}')
    return redirect('fintech:fintech-index')


@staff_member_required
def trigger_update_news(request):
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    try:
        call_command('update_news')
        messages.success(request, 'News-Update erfolgreich abgeschlossen.')
    except Exception as e:
        messages.error(request, f'Fehler beim News-Update: {e}')
    return redirect('fintech:fintech-index')


@staff_member_required
def trigger_refresh_week52(request):
    """Löscht alle abgelaufenen/ungültigen 52W-Einträge, damit sie beim nächsten
    Aufruf von /fintech/overall/ frisch von Yahoo/Comdirect geholt werden."""
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    try:
        deleted = 0
        skipped = 0
        from .models import FiftyTwoWeekRange
        for r in FiftyTwoWeekRange.objects.all():
            if r.skip_yahoo:
                skipped += 1
                continue  # Blacklist-Einträge nie löschen
            if r.is_expired():
                r.delete()
                deleted += 1
        messages.success(request, f'52W-Refresh: {deleted} Einträge gelöscht (wird neu geladen), {skipped} Blacklist-Einträge behalten.')
    except Exception as e:
        messages.error(request, f'Fehler beim 52W-Refresh: {e}')
    return redirect('fintech:fintech-index')


@never_cache
@staff_member_required
def clean_up(request):
    """Wartungswerkzeuge für Asset-Daten (Price Fetch Blocker zurücksetzen, DB-Cleanup)."""
    result = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "remove_price_fetch_blocker":
            count = Asset.objects.filter(price_fetch_blocked=True).update(
                price_fetch_blocked=False, price_fetch_failing_since=None
            )
            result = {"action": "remove_price_fetch_blocker", "count": count}
        elif action == "run_cleanup":
            try:
                call_command('clean_up')
                result = {"action": "run_cleanup", "ok": True}
            except Exception as e:
                result = {"action": "run_cleanup", "ok": False, "error": str(e)}
    return render(request, "fintech/clean_up.html", {"result": result})


BACKUP_MODELS_ALL = [
    FinConfig, Asset, Holdings, Price, Watchlist, WatchlistEntry,
    FiftyTwoWeekRange, NewsEvent, FondHolding, ManualFondHolding, NameAlias,
]
BACKUP_MODELS_KURSE = [Price]


def _model_to_csv_bytes(model) -> bytes:
    fields = [f.name for f in model._meta.fields]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in model.objects.all().values(*fields):
        writer.writerow(row)
    # utf-8-sig (BOM), damit Excel Umlaute korrekt anzeigt
    return buf.getvalue().encode("utf-8-sig")


@login_required
def backup_page(request):
    return render(request, "fintech/backup.html")


@never_cache
@login_required
def backup_download(request):
    mode = "kurse" if request.GET.get("mode") == "kurse" else "alle"
    models_to_export = BACKUP_MODELS_KURSE if mode == "kurse" else BACKUP_MODELS_ALL

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for model in models_to_export:
            zf.writestr(f"{model.__name__}.csv", _model_to_csv_bytes(model))

    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="fintech_backup_{mode}.zip"'
    return response


def portfolio_export(request):
    if not (_is_api_key_valid(request) or (request.user.is_active and request.user.is_staff)):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    fmt = request.GET.get("format", "json")
    timestamp = timezone.now().strftime('%Y-%m-%d_%H%M%S')

    if fmt == "yahoo_csv":
        csv_str, skipped = _build_yahoo_portfolio_csv()
        return render(request, "fintech/portfolio_export.html", {
            "format": "yahoo_csv",
            "csv_str": csv_str,
            "skipped": skipped,
            "download_filename": f"portfolio_yahoo_{timestamp}.csv",
        })

    data = list(PortfolioSummary.objects.portfolio())
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=decimal_serializer)

    return render(request, "fintech/portfolio_export.html", {
        "format": "json",
        "json_str": json_str,
        "download_filename": f"portfolio_export_{timestamp}.json",
    })


def _build_yahoo_portfolio_csv() -> Tuple[str, list]:
    """
    CSV im Yahoo-Finance-Portfolio-Import-Format: Symbol,Trade Date,Purchase Price,Quantity.
    "Trade Date" gibt es in Holdings nicht (nur ein aggregierter Bestand pro Asset, keine
    Einzeltransaktionen mit Datum, siehe csv_import.py) — Holdings.created_at (erster
    Bestandseintrag) ist die einzig verfügbare Näherung dafür.
    """
    holdings = list(
        Holdings.objects.filter(quantity__gt=Decimal('0'))
        .select_related('asset')
        .order_by('asset__name')
    )
    symbols = async_to_sync(_resolve_yahoo_symbols)([h.asset for h in holdings])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Symbol", "Trade Date", "Purchase Price", "Quantity"])

    skipped = []
    for h in holdings:
        symbol = symbols.get(h.asset.isin)
        if not symbol:
            skipped.append(f"{h.asset.isin} ({h.asset.name}): kein Yahoo-Symbol gefunden")
            continue
        if h.average_purchase_price is None:
            skipped.append(f"{h.asset.isin} ({h.asset.name}): kein Einkaufspreis hinterlegt")
            continue
        writer.writerow([
            symbol,
            h.created_at.strftime('%Y-%m-%d'),
            f"{h.average_purchase_price:.2f}",
            format(h.quantity.normalize(), 'f'),  # "10" statt "10.000000", aber "0.333333" bleibt exakt
        ])
    return buf.getvalue(), skipped


async def _resolve_yahoo_symbols(assets: list) -> dict:
    """ISIN -> Yahoo-Symbol für alle *assets*, parallel (gleiches Muster wie update_prices/Benchmark).
    Nutzt Asset.yahoo_symbol falls gesetzt, sonst Live-Suche — neu aufgelöste Symbole werden
    zurückgeschrieben, damit spätere Exporte/Kursabrufe dieselbe Suche nicht wiederholen müssen."""
    semaphore = asyncio.Semaphore(5)
    tasks = [_resolve_one_yahoo_symbol(asset, semaphore) for asset in assets]
    results = await asyncio.gather(*tasks)
    return dict(results)


async def _resolve_one_yahoo_symbol(asset, semaphore: asyncio.Semaphore):
    if asset.yahoo_symbol:
        return asset.isin, asset.yahoo_symbol

    async with semaphore:
        symbol = await asyncio.to_thread(_lookup_yahoo_symbol, asset.isin)

    if symbol:
        await sync_to_async(_save_yahoo_symbol)(asset, symbol)
    return asset.isin, symbol


def _lookup_yahoo_symbol(isin: str):
    from .apis.services.yahoo_finance import YahooFinanceRequest
    try:
        return YahooFinanceRequest()._isin2symbol(isin)
    except Exception as exc:
        logger.warning(f"Yahoo-Symbol-Suche fehlgeschlagen für {isin}: {exc}")
        return None


def _save_yahoo_symbol(asset, symbol: str) -> None:
    asset.yahoo_symbol = symbol
    asset.save(update_fields=["yahoo_symbol"])


def watchlist_export(request):
    if not (_is_api_key_valid(request) or (request.user.is_active and request.user.is_staff)):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    D = DecimalField(max_digits=10, decimal_places=4)

    entries = (
        WatchlistEntry.objects
        .select_related('asset', 'watchlist')
        .annotate(
            delta_perc_since_add=ExpressionWrapper(
                (
                    F('asset__current_price')
                    / NullIf(F('price_at_add'), Decimal('0'))
                    - Decimal('1')
                ) * Decimal('100'),
                output_field=D,
            )
        )
        .order_by(F('delta_perc_since_add').desc(nulls_last=True))
        .values(
            'watchlist__name',
            'asset__isin',
            'asset__name',
            'asset__asset_class',
            'asset__current_price',
            'asset__current_price_timestamp',
            'price_at_add',
            'added_at',
            'source',
            'notes',
            'delta_perc_since_add',
        )
    )

    data = list(entries)
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=decimal_serializer)
    return render(request, "fintech/portfolio_export.html", {"json_str": json_str})

@never_cache
@staff_member_required
def portfolio_import(request):
    call_command("update_prices")  # Preise vor Import aktualisieren, damit sie in der UI direkt sichtbar sind
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        dry_run  = request.POST.get("dry_run") == "on"

        if not csv_file:
            request.session["import_error"] = "Bitte eine CSV-Datei auswählen."
            return redirect("fintech:portfolio-import")

        if not csv_file.name.endswith(".csv"):
            request.session["import_error"] = "Nur CSV-Dateien werden unterstützt."
            return redirect("fintech:portfolio-import")

        try:
            content = csv_file.read().decode("utf-8")
        except UnicodeDecodeError:
            content = csv_file.read().decode("latin-1")

        result = import_transactions(content, dry_run=dry_run)

        request.session["import_result"] = {
            "total":    result.total,
            "imported": result.imported,
            "skipped":  result.skipped,
            "errors":   result.errors,
            "dry_run":  result.dry_run,
        }
        return redirect("fintech:portfolio-import")

    result_data = request.session.pop("import_result", None)
    error       = request.session.pop("import_error", None)
    return render(request, "fintech/portfolio_import.html", {
        "result": result_data,
        "error":  error,
    })


_WATCHLIST_IMPORT_EXAMPLE = json.dumps([
    {
        "watchlist": "Tech Favoriten",
        "isin": "US0378331005",
        "source": "Handelsblatt 2026-05-27",
        "notes": "Starkes Q1, KGV noch attraktiv"
    },
    {
        "watchlist": "Tech Favoriten",
        "isin": "DE000SAP0011",
        "name": "SAP SE",
        "asset_class": "STOCK",
        "source": "",
        "notes": "Auf Einstiegsniveau beobachten"
    },
    {
        "watchlist": "Tech Favoriten",
        "isin": "CH0102993182",
        "name": "TE Connectivity",
        "asset_class": "STOCK",
        "yahoo_symbol": "TEL",
        "notes": "Yahoos ISIN-Suche findet Auslandsnotierungen wie diese nicht — yahoo_symbol als manuelles Ticker-Override angeben"
    }
], indent=2, ensure_ascii=False)


@never_cache
@staff_member_required
def watchlist_import(request):
    if request.method != "POST":
        return render(request, "fintech/watchlist_import.html", {
            "example_json": _WATCHLIST_IMPORT_EXAMPLE,
            "submitted_json": "",
            "dry_run": True,
        })

    raw = request.POST.get("json_data", "").strip()
    dry_run = request.POST.get("dry_run") == "on"

    # JSON parsen
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            raise ValueError("Erwartet wird ein JSON-Array [ ... ]")
    except (json.JSONDecodeError, ValueError) as exc:
        return render(request, "fintech/watchlist_import.html", {
            "example_json": _WATCHLIST_IMPORT_EXAMPLE,
            "submitted_json": raw,
            "dry_run": dry_run,
            "error": f"Ungültiges JSON: {exc}",
        })

    total = len(entries)
    created = updated = 0
    errors = []
    details = []

    for idx, item in enumerate(entries, start=1):
        isin           = str(item.get("isin", "")).strip().upper()
        watchlist_name = str(item.get("watchlist", "")).strip()
        source         = str(item.get("source", "")).strip()
        notes          = str(item.get("notes", "")).strip()
        asset_name     = str(item.get("name", "")).strip() or isin
        asset_class    = str(item.get("asset_class", "STOCK")).strip().upper()
        yahoo_symbol   = str(item.get("yahoo_symbol", "")).strip() or None

        # Pflichtfelder prüfen
        if not isin:
            errors.append(f"Eintrag {idx}: 'isin' fehlt.")
            details.append({"isin": "–", "watchlist": watchlist_name, "status": "error", "price_at_add": None})
            continue
        if not watchlist_name:
            errors.append(f"Eintrag {idx} ({isin}): 'watchlist' fehlt.")
            details.append({"isin": isin, "watchlist": "–", "status": "error", "price_at_add": None})
            continue
        if not AssetClass.is_valid(asset_class):
            errors.append(
                f"Eintrag {idx} ({isin}): 'asset_class' ungültig: '{asset_class}'. "
                f"Erlaubt: {', '.join(AssetClass.values)}."
            )
            details.append({"isin": isin, "watchlist": watchlist_name, "status": "error", "price_at_add": None})
            continue

        try:
            # Asset suchen oder neu anlegen — ein NEUES Asset wird nur angelegt
            # (bzw. im Dry-Run als anlegbar gewertet), wenn der Kurs-Abruf
            # erfolgreich war. Schlägt er fehl, gilt der Eintrag als Fehler.
            resolution = resolve_asset_with_price(isin, asset_name, asset_class, dry_run=dry_run, yahoo_symbol=yahoo_symbol)
            if resolution.error:
                errors.append(f"Eintrag {idx} ({isin}): {resolution.error}")
                details.append({"isin": isin, "watchlist": watchlist_name, "status": "error", "price_at_add": None})
                continue

            if not dry_run:
                asset = resolution.asset  # garantiert gesetzt (sonst oben continue)
                asset_created = resolution.created
                if asset_created:
                    logger.info(f"Watchlist-Import: neues Asset angelegt: {isin} ({asset_name})")

                # Watchlist anlegen falls nicht vorhanden
                watchlist, _ = Watchlist.objects.get_or_create(
                    name=watchlist_name,
                    user=request.user,
                )

                existing = WatchlistEntry.objects.filter(watchlist=watchlist, asset=asset).first()
                if existing:
                    # Nur notes und source aktualisieren
                    existing.notes  = notes
                    existing.source = source
                    existing.save(update_fields=["notes", "source"])
                    updated += 1
                    details.append({"isin": isin, "watchlist": watchlist_name, "status": "updated", "price_at_add": existing.price_at_add})
                else:
                    entry = WatchlistEntry(watchlist=watchlist, asset=asset, source=source, notes=notes)
                    entry.save()   # price_at_add wird in save() auto-befüllt
                    created += 1
                    details.append({"isin": isin, "watchlist": watchlist_name, "status": "created", "price_at_add": entry.price_at_add})
            else:
                # Dry-Run: nur prüfen ob Eintrag schon existiert
                wl_exists = Watchlist.objects.filter(name=watchlist_name, user=request.user).first()
                if resolution.created:
                    # Asset ist neu (Kurs-Abruf war erfolgreich) — kann noch keinen Eintrag haben
                    existing = None
                    preview_price = resolution.price
                else:
                    existing = (
                        WatchlistEntry.objects.filter(watchlist=wl_exists, asset=resolution.asset).first()
                        if wl_exists else None
                    )
                    # Preis bleibt bei einem Update unverändert — Vorschau zeigt den
                    # bestehenden price_at_add, nicht den aktuellen Kurs.
                    preview_price = existing.price_at_add if existing else resolution.price
                status = "updated" if existing else "created"
                if existing:
                    updated += 1
                else:
                    created += 1
                details.append({"isin": isin, "watchlist": watchlist_name, "status": status, "price_at_add": preview_price})
        except Exception as exc:
            logger.exception(f"Watchlist-Import: Fehler bei Eintrag {idx} ({isin})")
            errors.append(f"Eintrag {idx} ({isin}): {exc}")
            details.append({"isin": isin, "watchlist": watchlist_name, "status": "error", "price_at_add": None})
            continue

    result = {
        "total":   total,
        "created": created,
        "updated": updated,
        "errors":  errors,
        "details": details,
        "dry_run": dry_run,
    }
    return render(request, "fintech/watchlist_import.html", {
        "example_json":   _WATCHLIST_IMPORT_EXAMPLE,
        "submitted_json": raw,
        "dry_run":        dry_run,
        "result":         result,
    })


# ---------------------------------------------------------------------------
# Watchlist Performance
# ---------------------------------------------------------------------------

HYPOTHETICAL_INVESTMENT = Decimal("10000")  # EUR pro Eintrag


def _entry_perf(entry):
    """
    Berechnet Performance-Kennzahlen für einen WatchlistEntry.
    Gibt None zurück wenn Kurs-Daten fehlen.
    """
    price_add = entry.price_at_add
    price_now = entry.asset.current_price
    if not price_add or not price_now or price_add == 0:
        return None

    try:
        price_add = Decimal(str(price_add))
        price_now = Decimal(str(price_now))
        ratio = price_now / price_add
        current_value = HYPOTHETICAL_INVESTMENT * ratio
        simple_return = ratio - 1

        # Haltedauer in Tagen (mind. 1)
        added_at = entry.added_at
        if hasattr(added_at, 'date'):
            added_at = added_at.date()
        days_held = max((timezone.now().date() - added_at).days, 1)

        # Annualisierte Rendite (CAGR)
        annualized = float(ratio) ** (365.0 / days_held) - 1

        return {
            "current_value":   current_value,
            "simple_return":   simple_return,
            "annualized":      Decimal(str(round(annualized, 6))),
            "days_held":       days_held,
        }
    except (InvalidOperation, ZeroDivisionError, OverflowError):
        return None


@login_required
def watchlist_performance(request):
    """Übersicht: alle Watchlisten mit annualisierter Performance."""
    watchlists = Watchlist.objects.prefetch_related(
        "entries__asset"
    ).order_by("name")

    rows = []
    for wl in watchlists:
        entries = list(wl.entries.select_related("asset").all())
        total_invested = Decimal("0")
        total_current  = Decimal("0")
        weighted_days  = Decimal("0")
        valid_count    = 0

        for entry in entries:
            perf = _entry_perf(entry)
            if perf is None:
                continue
            total_invested += HYPOTHETICAL_INVESTMENT
            total_current  += perf["current_value"]
            weighted_days  += HYPOTHETICAL_INVESTMENT * perf["days_held"]
            valid_count    += 1

        if valid_count == 0 or total_invested == 0:
            rows.append({
                "name":        wl.name,
                "entry_count": len(entries),
                "valid_count": 0,
                "annualized":  None,
                "simple":      None,
                "gain_abs":    None,
            })
            continue

        simple = total_current / total_invested - 1
        avg_days = float(weighted_days / total_invested)
        try:
            annualized = float(total_current / total_invested) ** (365.0 / max(avg_days, 1)) - 1
            annualized_display = Decimal(str(round(annualized * 100, 2)))
        except OverflowError:
            # Extremer Kurssprung bei sehr frisch hinzugefügtem Eintrag (avg_days nahe 0)
            # lässt die Hochrechnung auf 365 Tage den float-Wertebereich sprengen.
            annualized_display = None

        # Für die Sortierung dieselbe Kennzahl verwenden, die auf der Karte auch
        # angezeigt wird (p.a. ab 365 Tagen Haltedauer, sonst einfache Gesamtrendite) —
        # sonst weicht die Reihenfolge von den sichtbaren Prozentwerten ab.
        display_value = (
            annualized_display
            if annualized_display is not None and round(avg_days) >= 365
            else simple * 100
        )

        rows.append({
            "name":           wl.name,
            "entry_count":    len(entries),
            "valid_count":    valid_count,
            "total_invested": total_invested,
            "total_current":  total_current,
            "gain_abs":       total_current - total_invested,
            "simple":         simple * 100,
            "annualized":     annualized_display,
            "avg_days":       round(avg_days),
            "sort_value":     display_value,
        })

    rows.sort(key=lambda r: r.get("sort_value", Decimal("-999")), reverse=True)
    return render(request, "fintech/watchlist_performance.html", {"rows": rows})


# ---------------------------------------------------------------------------
# Portfolio Performance (nach Kategorie)
# ---------------------------------------------------------------------------

# Slug ↔ Kategorie-ID Mapping (nur neue Kategorien 20–37)
_NEW_CATEGORIES = [v for v, _ in CategoryClass.choices if v >= 20]
_SLUG_TO_ID  = {slugify(CategoryClass(v).label): v for v in _NEW_CATEGORIES}
_ID_TO_SLUG  = {v: slugify(CategoryClass(v).label) for v in _NEW_CATEGORIES}
# Alphabetisch sortierte Liste für Prev/Next
_SORTED_SLUGS = sorted(_SLUG_TO_ID.keys())


_openfigi = OpenFigiService()

TOP_N = 10


@login_required
def portfolio_winners(request):
    """4-Spalten-Übersicht: Tages/Gesamt-Top5 und -Flop5."""
    today = timezone.now().date()
    yesterday_sq = Price.objects.filter(
        asset=OuterRef('asset_id'),
        timestamp__date__lt=today,
    ).order_by('-timestamp').values('current_price')[:1]

    holdings = (
        Holdings.objects
        .select_related('asset')
        .filter(category__gte=20, quantity__gt=0)
        .annotate(yesterday_price=Subquery(
            yesterday_sq, output_field=DecimalField(max_digits=20, decimal_places=4)
        ))
    )

    rows = []
    for h in holdings:
        invested   = (h.average_purchase_price or Decimal('0')) * h.quantity
        cur_price  = h.asset.current_price or Decimal('0')
        yest_price = getattr(h, 'yesterday_price', None) or Decimal('0')
        current    = cur_price  * h.quantity
        yesterday  = yest_price * h.quantity

        total_perc = (current / invested  - 1) * 100 if invested  > 0 else None
        day_perc   = (current / yesterday - 1) * 100 if yesterday > 0 else None

        rows.append({
            'name':        h.asset.name,
            'isin':        h.asset.isin,
            'symbol':      h.asset.symbol or '',
            'logo':        h.asset.logo   or '',
            'asset_class': h.asset.asset_class,
            'holdings_id': h.pk,
            'total_perc':  total_perc,
            'day_perc':    day_perc,
            'invested':    invested  if invested  > 0 else None,
            'current':     current   if cur_price > 0 else None,
            'yesterday':   yesterday if yest_price > 0 else None,
        })

    def top(lst, key, reverse=True):
        valid = [r for r in lst if r[key] is not None]
        return sorted(valid, key=lambda r: r[key], reverse=reverse)[:TOP_N]

    # Summary-Daten
    total_inv  = sum(r['invested']   for r in rows if r['invested']   is not None)
    total_cur  = sum(r['current']    for r in rows if r['current']    is not None)
    total_yest = sum(r['yesterday']  for r in rows if r['yesterday']  is not None)

    return render(request, 'fintech/portfolio_winners.html', {
        'day_best':      top(rows, 'day_perc',   reverse=True),
        'total_best':    top(rows, 'total_perc', reverse=True),
        'total_worst':   top(rows, 'total_perc', reverse=False),
        'day_worst':     top(rows, 'day_perc',   reverse=False),
        'total_inv':     total_inv,
        'total_cur':     total_cur,
        'total_yest':    total_yest,
        'gain_total':    total_cur - total_inv,
        'simple_total':  (total_cur / total_inv  - 1) * 100 if total_inv  else None,
        'day_abs_total': total_cur - total_yest            if total_yest else None,
        'day_pct_total': (total_cur / total_yest - 1) * 100 if total_yest else None,
    })


def _fetch_missing_symbols(holdings):
    """
    Prüft alle STOCK-Holdings ohne Symbol und holt sie via OpenFIGI (Batch).
    Speichert gefundene Symbole direkt in Asset.symbol.
    """
    missing = [
        h.asset for h in holdings
        if h.asset.asset_class == 'STOCK' and not h.asset.symbol
    ]
    if not missing:
        return

    isins = [a.isin for a in missing]
    logger.info(f"OpenFIGI: Symbol-Lookup für {len(isins)} Assets: {isins}")

    symbol_map = _openfigi.isin2symbol_batch(isins)

    for asset in missing:
        symbol = symbol_map.get(asset.isin)
        if symbol:
            asset.symbol = symbol
            asset.save(update_fields=['symbol'])
            logger.info(f"Symbol gespeichert: {asset.isin} → {symbol}")
        else:
            logger.warning(f"Kein Symbol gefunden für {asset.isin} ({asset.name})")


@login_required
def portfolio_performance(request):
    """Übersicht: alle neuen Kategorien mit Gesamt- und Tagesperformance."""
    today = timezone.now().date()

    # Yesterday-Price Subquery
    yesterday_sq = Price.objects.filter(
        asset=OuterRef('asset_id'),
        timestamp__date__lt=today,
    ).order_by('-timestamp').values('current_price')[:1]

    holdings = (
        Holdings.objects
        .select_related('asset')
        .filter(category__gte=20, quantity__gt=0)
        .annotate(yesterday_price=Subquery(yesterday_sq, output_field=DecimalField(max_digits=20, decimal_places=4)))
        .order_by('category', 'asset__name')
    )

    cat_labels = {v: label for v, label in CategoryClass.choices}

    groups = {}
    for h in holdings:
        cat = h.category
        if cat not in groups:
            groups[cat] = {
                'category':        cat,
                'label':           cat_labels.get(cat, str(cat)),
                'count':           0,
                'total_invested':  Decimal('0'),
                'total_current':   Decimal('0'),
                'total_yesterday': Decimal('0'),
            }
        g = groups[cat]
        g['count'] += 1

        qty       = h.quantity
        invested  = (h.average_purchase_price or Decimal('0')) * qty
        current   = (h.asset.current_price    or Decimal('0')) * qty
        yesterday = (h.yesterday_price        or Decimal('0')) * qty

        g['total_invested']  += invested
        g['total_current']   += current
        g['total_yesterday'] += yesterday

    rows = []
    for g in groups.values():
        inv  = g['total_invested']
        cur  = g['total_current']
        yest = g['total_yesterday']

        simple   = (cur / inv  - 1) * 100 if inv  > 0 else None
        gain_abs = cur - inv              if inv  > 0 else None
        day_perc = (cur / yest - 1) * 100 if yest > 0 else None
        day_abs  = cur - yest             if yest > 0 else None

        rows.append({
            'category':        g['category'],
            'slug':            _ID_TO_SLUG.get(g['category'], str(g['category'])),
            'label':           g['label'],
            'count':           g['count'],
            'total_invested':  inv,
            'total_current':   cur,
            'gain_abs':        gain_abs,
            'simple':          simple,
            'day_perc':        day_perc,
            'day_abs':         day_abs,
        })

    rows.sort(key=lambda r: r['simple'] if r['simple'] is not None else Decimal('-999'), reverse=True)

    total_inv  = sum(r['total_invested'] for r in rows)
    total_cur  = sum(r['total_current']  for r in rows)
    total_yest = sum(g['total_yesterday'] for g in groups.values())

    return render(request, 'fintech/portfolio_performance.html', {
        'rows':          rows,
        'total_inv':     total_inv,
        'total_cur':     total_cur,
        'total_yest':    total_yest,
        'gain_total':    total_cur - total_inv,
        'simple_total':  (total_cur / total_inv  - 1) * 100 if total_inv  else None,
        'day_total':     (total_cur / total_yest - 1) * 100 if total_yest else None,
        'day_abs_total': total_cur - total_yest            if total_yest else None,
    })


@login_required
def portfolio_category_detail(request, category_slug):
    """Drill-down: alle Holdings einer Kategorie (per Slug)."""
    category_id = _SLUG_TO_ID.get(category_slug)
    if category_id is None:
        raise Http404(f"Kategorie '{category_slug}' nicht gefunden.")

    label = CategoryClass(category_id).label

    # Prev / Next (alphabetisch)
    idx = _SORTED_SLUGS.index(category_slug)
    prev_slug = _SORTED_SLUGS[idx - 1] if idx > 0 else None
    next_slug = _SORTED_SLUGS[idx + 1] if idx < len(_SORTED_SLUGS) - 1 else None

    today = timezone.now().date()
    yesterday_sq = Price.objects.filter(
        asset=OuterRef('asset_id'),
        timestamp__date__lt=today,
    ).order_by('-timestamp').values('current_price')[:1]

    holdings = (
        Holdings.objects
        .select_related('asset')
        .filter(category=category_id, quantity__gt=0)
        .annotate(yesterday_price=Subquery(yesterday_sq, output_field=DecimalField(max_digits=20, decimal_places=4)))
        .order_by('asset__name')
    )

    # ── Symbol-Lookup via OpenFIGI für Stocks ohne Symbol ────────────────
    _fetch_missing_symbols(holdings)

    rows = []
    for h in holdings:
        invested   = (h.average_purchase_price or Decimal('0')) * h.quantity
        cur_price  = h.asset.current_price or Decimal('0')
        yest_price = getattr(h, 'yesterday_price', None) or Decimal('0')
        current    = cur_price  * h.quantity
        yesterday  = yest_price * h.quantity

        simple   = (current / invested  - 1) * 100 if invested  > 0 else None
        gain_abs = current - invested              if invested  > 0 else None
        day_perc = (current / yesterday - 1) * 100 if yesterday > 0 else None
        day_abs  = current - yesterday             if yesterday > 0 else None

        rows.append({
            'holdings_id':    h.pk,
            'asset_id':       h.asset.pk,
            'name':           h.asset.name,
            'isin':           h.asset.isin,
            'symbol':         h.asset.symbol or '',
            'logo':           h.asset.logo or '',
            'asset_class':    h.asset.asset_class,
            'quantity':       h.quantity,
            'avg_price':      h.average_purchase_price,
            'current_price':  h.asset.current_price,
            'yesterday_price': yest_price if yest_price else None,
            'invested':       invested,
            'current':        current,
            'gain_abs':       gain_abs,
            'simple':         simple,
            'day_perc':       day_perc,
            'day_abs':        day_abs,
            'not_for_sale':   h.not_for_sale,
            'stake_recovered': h.stake_recovered,
        })

    rows.sort(key=lambda r: r['simple'] if r['simple'] is not None else Decimal('-999'), reverse=True)

    total_inv = sum(r['invested'] for r in rows)
    total_cur = sum(r['current']  for r in rows)

    total_yest = sum(r['day_abs'] + r['current'] if r['day_abs'] is not None else r['current'] for r in rows)
    # Simpler: sum of yesterday values
    total_yest = sum((r['yesterday_price'] or Decimal('0')) * 1 for r in rows)
    # Actually recompute properly
    total_yest = Decimal('0')
    for r in rows:
        yp = r['yesterday_price']
        if yp:
            # yesterday_price is price per share, multiply by qty
            pass  # already computed as 'current - day_abs'
        if r['day_abs'] is not None:
            total_yest += r['current'] - r['day_abs']

    day_total_abs = total_cur - total_yest if total_yest else None
    day_total_pct = (total_cur / total_yest - 1) * 100 if total_yest else None

    return render(request, 'fintech/portfolio_category_detail.html', {
        'label':         label,
        'category_slug': category_slug,
        'rows':          rows,
        'total_inv':     total_inv,
        'total_cur':     total_cur,
        'gain_total':    total_cur - total_inv,
        'simple_total':  (total_cur / total_inv - 1) * 100 if total_inv else None,
        'day_total_abs': day_total_abs,
        'day_total_pct': day_total_pct,
        'prev_slug':     prev_slug,
        'next_slug':     next_slug,
        'prev_label':    CategoryClass(_SLUG_TO_ID[prev_slug]).label if prev_slug else None,
        'next_label':    CategoryClass(_SLUG_TO_ID[next_slug]).label if next_slug else None,
    })


@login_required
def watchlist_detail(request, watchlist_name):
    """Drill-down: Einzelpositionen einer Watchlist mit Performance."""
    wl = get_object_or_404(Watchlist, name=watchlist_name)
    entries = wl.entries.select_related("asset").order_by("asset__name")

    reset_result = request.session.pop("watchlist_reset_result", None)
    failed_isins = set(reset_result["failed"]) if reset_result else set()

    entry_rows = []
    for entry in entries:
        perf = _entry_perf(entry)
        entry_rows.append({
            "isin":          entry.asset.isin,
            "name":          entry.asset.name,
            "symbol":        entry.asset.symbol,
            "logo":          entry.asset.logo,
            "asset_class":   entry.asset.asset_class,
            "price_at_add":  entry.price_at_add,
            "current_price": entry.asset.current_price,
            "added_at":      entry.added_at,
            "source":        entry.source,
            "notes":         entry.notes,
            "days_held":     perf["days_held"]    if perf else None,
            "current_value": perf["current_value"] if perf else None,
            "simple":        perf["simple_return"] * 100 if perf else None,
            "annualized":    perf["annualized"] * 100    if perf else None,
            "has_price":     perf is not None,
            "reset_failed":  entry.asset.isin in failed_isins,
        })

    entry_rows.sort(
        key=lambda r: r["annualized"] if r["annualized"] is not None else Decimal("-999"),
        reverse=True,
    )

    return render(request, "fintech/watchlist_detail.html", {
        "watchlist": wl,
        "entry_rows": entry_rows,
        "hypothetical": HYPOTHETICAL_INVESTMENT,
        "reset_result": reset_result,
    })


@login_required
def watchlist_delete(request, watchlist_name):
    """Löscht eine komplette Watchlist inkl. aller Einträge (Cascade). Unwiderruflich."""
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

    wl = get_object_or_404(Watchlist, name=watchlist_name)
    entry_count = wl.entries.count()
    wl.delete()
    messages.success(request, f'Watchlist "{watchlist_name}" mit {entry_count} Eintrag(en) wurde gelöscht.')
    return redirect("fintech:watchlist-performance")


@login_required
def watchlists_all(request):
    """
    Alle Einträge aus ALLEN Watchlisten in einer Tabelle — wie watchlist_detail,
    aber mit einer Watchlist-Namen-Spalte statt Quelle, sortierbar per JS
    (Name / Einfach / p.a.) über data-*-Attribute auf jeder Zeile.
    """
    entries = WatchlistEntry.objects.select_related("asset", "watchlist").order_by("asset__name")

    entry_rows = []
    for entry in entries:
        perf = _entry_perf(entry)
        simple = perf["simple_return"] * 100 if perf else None
        annualized = perf["annualized"] * 100 if perf else None
        entry_rows.append({
            "isin":            entry.asset.isin,
            "name":            entry.asset.name,
            "symbol":          entry.asset.symbol,
            "logo":            entry.asset.logo,
            "asset_class":     entry.asset.asset_class,
            "watchlist_name":  entry.watchlist.name,
            "price_at_add":    entry.price_at_add,
            "current_price":   entry.asset.current_price,
            "added_at":        entry.added_at,
            "notes":           entry.notes,
            "days_held":       perf["days_held"]    if perf else None,
            "current_value":   perf["current_value"] if perf else None,
            "simple":          simple,
            "annualized":      annualized,
            # Für client-seitiges Sortieren: garantiert punkt-dezimal, kein
            # lokalisiertes Komma wie es {{ row.simple }} im Template hätte.
            "simple_sort":     str(float(simple)) if simple is not None else "-999999",
            "annualized_sort": str(float(annualized)) if annualized is not None else "-999999",
        })

    entry_rows.sort(
        key=lambda r: r["annualized"] if r["annualized"] is not None else Decimal("-999"),
        reverse=True,
    )

    return render(request, "fintech/watchlists_all.html", {
        "entry_rows": entry_rows,
        "hypothetical": HYPOTHETICAL_INVESTMENT,
    })


@login_required
def watchlist_reset_prices(request, watchlist_name):
    """
    Setzt für ALLE Einträge einer Watchlist den Einstiegspreis (price_at_add)
    auf den aktuellen Kurs zurück. Holt dafür je Asset aktiv einen frischen
    Kurs. Schlägt der Abruf für ein Asset fehl, bleibt dessen Einstiegspreis
    unverändert und wird auf der Detailseite rot markiert.
    """
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

    wl = get_object_or_404(Watchlist, name=watchlist_name)
    entries = wl.entries.select_related("asset")

    ok = 0
    failed_isins = []
    failures = []
    for entry in entries:
        price = refresh_asset_price(entry.asset, failures)
        if price is None:
            failed_isins.append(entry.asset.isin)
            continue
        entry.price_at_add = price
        entry.save(update_fields=["price_at_add"])
        ok += 1

    report_price_fetch_failures(failures)

    request.session["watchlist_reset_result"] = {"ok": ok, "failed": failed_isins}
    return redirect("fintech:watchlist-detail", watchlist_name=watchlist_name)


@login_required
def news(request):
    if request.method == "POST":
        pk = request.POST.get("mark_read")
        if pk:
            NewsEvent.objects.filter(pk=pk).update(is_read=True)
        mark_all = request.POST.get("mark_all_read")
        if mark_all:
            NewsEvent.objects.filter(is_read=False).update(is_read=True)
        return redirect("fintech:news")

    show_all = request.GET.get("all") == "1"
    qs = NewsEvent.objects.prefetch_related("assets")
    if not show_all:
        qs = qs.filter(is_read=False)

    events = list(qs[:200])
    unread_count = NewsEvent.objects.filter(is_read=False).count()

    return render(request, "fintech/news.html", {
        "events":      events,
        "show_all":    show_all,
        "unread_count": unread_count,
    })


@login_required
def news_feed(request):
    """
    RSS-Reader-artiger News-Feed für gehaltene Aktien (Yahoo Finance + Google
    News RSS, periodisch via update_news-Command befüllt — siehe dort für die
    Auswahl der Unternehmen). Optional per ?company=<isin> auf ein Unternehmen
    gefiltert.
    """
    articles = NewsArticle.objects.select_related("asset")

    company_filter = request.GET.get("company", "").strip()
    if company_filter:
        articles = articles.filter(asset__isin=company_filter)

    articles = list(articles[:150])

    # Für den Filter-Dropdown: alle Unternehmen, die aktuell News im Feed haben.
    companies = (
        NewsArticle.objects.exclude(asset__isnull=True)
        .values_list("asset__isin", "asset__name")
        .distinct()
        .order_by("asset__name")
    )

    return render(request, "fintech/news_feed.html", {
        "articles": articles,
        "companies": companies,
        "company_filter": company_filter,
        "total_count": NewsArticle.objects.count(),
    })


@login_required
def alarme(request):
    if request.method == "POST":
        if "create_alarm" in request.POST:
            isin = request.POST.get("asset")
            target_price = request.POST.get("target_price")
            asset = Asset.objects.filter(isin=isin).first()
            if asset and target_price:
                try:
                    PriceAlarm.objects.create(asset=asset, target_price=Decimal(target_price))
                except (InvalidOperation, ValueError):
                    messages.error(request, "Ungültiger Kurswert.")
        elif "deactivate_alarm" in request.POST:
            pk = request.POST.get("deactivate_alarm")
            PriceAlarm.objects.filter(pk=pk).update(is_active=False)
        elif "create_trailing_stop" in request.POST:
            isin = request.POST.get("ts_asset")
            trail_percent = request.POST.get("trail_percent") or "10"
            holding = Holdings.objects.filter(asset__isin=isin).select_related("asset").first()
            if holding is None:
                messages.error(request, "Kein Bestand für dieses Asset gefunden.")
            elif not holding.asset.current_price:
                messages.error(request, "Kein aktueller Kurs für dieses Asset verfügbar.")
            else:
                try:
                    pct = Decimal(trail_percent)
                    TrailingStopLoss.objects.update_or_create(
                        holdings=holding,
                        defaults={
                            "trail_percent": pct,
                            "activated_price": holding.asset.current_price,
                            "reference_price": holding.asset.current_price,
                            "is_active": True,
                        },
                    )
                except (InvalidOperation, ValueError):
                    messages.error(request, "Ungültiger Prozentwert.")
        elif "deactivate_trailing_stop" in request.POST:
            pk = request.POST.get("deactivate_trailing_stop")
            TrailingStopLoss.objects.filter(pk=pk).update(is_active=False)
        return redirect("fintech:alarme")

    # Assets, für die überhaupt Kurse aktualisiert werden (Holdings/Watchlist) —
    # nur für diese kann ein Alarm sinnvoll auslösen, siehe update_prices._get_assets_to_update.
    tracked_assets = (
        Asset.objects.filter(Q(holdings__isnull=False) | Q(watchlistentry__isnull=False))
        .distinct()
        .order_by("name")
    )
    # Trailing-Stop macht nur für echte Bestände Sinn (quantity > 0), nicht für
    # Dummy-Holdings (quantity=0, nur für den Aktien-Look-Through angelegt).
    held_assets = (
        Asset.objects.filter(holdings__quantity__gt=0)
        .distinct()
        .order_by("name")
    )

    price_events = [
        {"kind": "price_alarm", "triggered_at": e.triggered_at, "obj": e}
        for e in PriceAlarmEvent.objects.select_related("asset")[:20]
    ]
    trailing_events = [
        {"kind": "trailing_stop", "triggered_at": e.triggered_at, "obj": e}
        for e in TrailingStopEvent.objects.select_related("asset")[:20]
    ]
    combined_events = sorted(price_events + trailing_events, key=lambda r: r["triggered_at"], reverse=True)[:20]

    return render(request, "fintech/alarme.html", {
        "events": combined_events,
        "active_alarms": PriceAlarm.objects.filter(is_active=True).select_related("asset"),
        "active_trailing_stops": TrailingStopLoss.objects.filter(is_active=True).select_related("holdings__asset"),
        "tracked_assets": tracked_assets,
        "held_assets": held_assets,
    })


@csrf_exempt
def _notify_pending_events(queryset, format_fn, trigger):
    """Verschickt Telegram für alle Events einer Queryset mit notified_at=NULL."""
    pending = list(queryset.filter(notified_at__isnull=True).order_by("triggered_at")[:100])
    sent = failed = 0
    for event in pending:
        if send_telegram_message(format_fn(event), trigger=trigger):
            event.notified_at = timezone.now()
            event.save(update_fields=["notified_at"])
            sent += 1
        else:
            failed += 1
    return len(pending), sent, failed


def notify_price_alarms(request):
    """
    Holt Telegram-Versand für PriceAlarmEvent/TrailingStopEvent nach, die
    entstanden sind, ohne dass die Nachricht direkt verschickt werden konnte —
    z.B. weil Price.save() im update_prices-Lauf auf GitHub Actions ausgeführt
    wurde, wo keine TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID konfiguriert sind
    (bewusst so, um den Telegram-Bot-Token nicht zusätzlich als GitHub-Secret
    duplizieren zu müssen). Auth wie die anderen fintech-Export-Endpoints:
    X-Api-Key oder Staff-Login.
    """
    if not (_is_api_key_valid(request) or (request.user.is_active and request.user.is_staff)):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])

    pa_pending, pa_sent, pa_failed = _notify_pending_events(
        PriceAlarmEvent.objects.select_related("asset"), format_price_alarm_message, "price_alarm",
    )
    ts_pending, ts_sent, ts_failed = _notify_pending_events(
        TrailingStopEvent.objects.select_related("asset"), format_trailing_stop_message, "trailing_stop",
    )

    return JsonResponse({
        "pending": pa_pending + ts_pending,
        "sent": pa_sent + ts_sent,
        "failed": pa_failed + ts_failed,
        "price_alarms": {"pending": pa_pending, "sent": pa_sent, "failed": pa_failed},
        "trailing_stops": {"pending": ts_pending, "sent": ts_sent, "failed": ts_failed},
    })


@staff_member_required
def manual_fund_holdings_edit(request, isin=None):
    """
    Formularseite zum halb-manuellen Pflegen von ManualFondHolding-Einträgen
    für einen Fonds (z.B. aus einem Factsheet abgetippte Top-Holdings für
    aktiv gemanagte Fonds ohne strukturierte Datenquelle wie JustETF/DAX/
    MSCI-World-Tail). Ersetzt beim Speichern ALLE bestehenden Einträge für
    diesen Fonds durch die eingegebene Tabelle (kein inkrementelles
    Hinzufügen — die Tabelle ist der gewünschte Gesamtzustand).
    """
    funds = Asset.objects.filter(
        asset_class__in=[AssetClass.ETF, AssetClass.FOND],
    ).order_by('name')

    fund = None
    if isin:
        fund = get_object_or_404(
            Asset, isin=isin.upper(), asset_class__in=[AssetClass.ETF, AssetClass.FOND],
        )

    if request.method == 'POST' and fund is not None:
        names = request.POST.getlist('holding_name')
        percentages = request.POST.getlist('percentage')

        new_entries = []
        errors = []
        for name, pct_raw in zip(names, percentages):
            name = name.strip()
            pct_raw = pct_raw.strip().replace(',', '.')
            if not name and not pct_raw:
                continue
            if not name or not pct_raw:
                errors.append(f"Zeile unvollständig: Name={name!r}, Anteil={pct_raw!r}")
                continue
            try:
                percentage = Decimal(pct_raw)
            except InvalidOperation:
                errors.append(f"Ungültiger Anteil bei '{name}': {pct_raw!r}")
                continue
            if percentage < 0 or percentage > 100:
                errors.append(f"Anteil außerhalb 0-100 bei '{name}': {percentage}")
                continue
            new_entries.append(ManualFondHolding(fund=fund, holding_name=name, percentage=percentage))

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            with transaction.atomic():
                ManualFondHolding.objects.filter(fund=fund).delete()
                ManualFondHolding.objects.bulk_create(new_entries)
            messages.success(request, f"{len(new_entries)} Position(en) für {fund.name} gespeichert.")
            return redirect('fintech:manual-fund-holdings-edit', isin=fund.isin)

    existing_entries = []
    if fund is not None:
        existing_entries = list(ManualFondHolding.objects.filter(fund=fund).order_by('-percentage'))

    empty_rows_needed = max(5, 15 - len(existing_entries))

    return render(request, 'fintech/manual_fund_holdings_edit.html', {
        'funds':           funds,
        'fund':            fund,
        'existing_entries': existing_entries,
        'empty_row_range': range(empty_rows_needed),
    })
