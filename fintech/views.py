from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.conf import settings
from django.db.models import F, ExpressionWrapper, DecimalField
from django.db.models.functions import NullIf
from .model_views import PortfolioSummary
from .models import Price
from django.db.models import OuterRef, Subquery
from .models import WatchlistEntry, Watchlist, Asset, Holdings
from .models_helper.category_class import CategoryClass
from django.utils.text import slugify
from django.http import Http404
from .apis.services.openfigi import OpenFigiService
import json
from decimal import Decimal, InvalidOperation
from .apis.services.csv_import import import_transactions
from django.contrib import messages
from django.core.management import call_command
from django.views.decorators.cache import never_cache
from django.utils import timezone

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

def portfolio_export(request):
    if not (_is_api_key_valid(request) or (request.user.is_active and request.user.is_staff)):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = list(PortfolioSummary.objects.portfolio())
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=decimal_serializer)
    return render(request, "fintech/portfolio_export.html", {"json_str": json_str})


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

        # Pflichtfelder prüfen
        if not isin:
            errors.append(f"Eintrag {idx}: 'isin' fehlt.")
            details.append({"isin": "–", "watchlist": watchlist_name, "status": "error", "price_at_add": None})
            continue
        if not watchlist_name:
            errors.append(f"Eintrag {idx} ({isin}): 'watchlist' fehlt.")
            details.append({"isin": isin, "watchlist": "–", "status": "error", "price_at_add": None})
            continue

        # Asset suchen oder neu anlegen
        if not dry_run:
            asset, asset_created = Asset.objects.get_or_create(
                isin=isin,
                defaults={"name": asset_name, "asset_class": asset_class},
            )
            if asset_created:
                logger.info(f"Watchlist-Import: neues Asset angelegt: {isin} ({asset_name})")
        else:
            # Dry-Run: nur prüfen ob Asset existiert
            asset = Asset.objects.filter(isin=isin).first()
            asset_created = asset is None

        if not dry_run:
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
            already_in = (
                WatchlistEntry.objects.filter(watchlist=wl_exists, asset=asset).exists()
                if (wl_exists and asset) else False
            )
            status = "updated" if already_in else "created"
            if already_in:
                updated += 1
            else:
                created += 1
            current_price = asset.current_price if asset else None
            details.append({"isin": isin, "watchlist": watchlist_name, "status": status, "price_at_add": current_price})

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
    except (InvalidOperation, ZeroDivisionError):
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
        annualized = float(total_current / total_invested) ** (365.0 / max(avg_days, 1)) - 1

        rows.append({
            "name":           wl.name,
            "entry_count":    len(entries),
            "valid_count":    valid_count,
            "total_invested": total_invested,
            "total_current":  total_current,
            "gain_abs":       total_current - total_invested,
            "simple":         simple * 100,
            "annualized":     Decimal(str(round(annualized * 100, 2))),
            "avg_days":       round(avg_days),
        })

    rows.sort(key=lambda r: r["annualized"] if r["annualized"] is not None else Decimal("-999"), reverse=True)
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
        .filter(category__gte=20)
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
        .filter(category__gte=20)
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
        .filter(category=category_id)
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

    entry_rows = []
    for entry in entries:
        perf = _entry_perf(entry)
        entry_rows.append({
            "isin":          entry.asset.isin,
            "name":          entry.asset.name,
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
        })

    entry_rows.sort(
        key=lambda r: r["annualized"] if r["annualized"] is not None else Decimal("-999"),
        reverse=True,
    )

    return render(request, "fintech/watchlist_detail.html", {
        "watchlist": wl,
        "entry_rows": entry_rows,
        "hypothetical": HYPOTHETICAL_INVESTMENT,
    })
