"""
Gemeinsame Business-Logik für Asset-Anlage mit Kurs-Abruf.

Wird sowohl vom Watchlist-API-Endpoint (apis/watchlist_api.py) als auch vom
Watchlist-Import (views.watchlist_import) verwendet, damit ein neues Asset nie
ohne aktuellen Kurs angelegt wird — schlägt der Kurs-Abruf fehl, wird nichts
gespeichert.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from typing import NamedTuple, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from core.jira_client import JiraClient, JiraApiError

from .apis.services.provider_manager import ProviderManager
from .apis.services.name_matching import match_held_stock, load_aliases
from .models import Asset, Price, Holdings, FondHolding, ManualFondHolding
from .models_helper.asset_class import AssetClass
from .models_helper.category_class import CategoryClass

logger = logging.getLogger(__name__)

_provider_manager = ProviderManager()

# Ein einzelner fehlgeschlagener Abruf (z.B. kurzer Provider-Hänger) soll noch
# kein Ticket auslösen. Erst wenn ein Asset ununterbrochen länger als diese
# Dauer fehlschlägt, wird price_fetch_blocked gesetzt und gemeldet.
PRICE_FETCH_FAILURE_THRESHOLD = timedelta(hours=24)


class AssetResolution(NamedTuple):
    asset: Optional[Asset]
    created: bool
    price: Optional[Decimal]
    error: Optional[str]


def resolve_asset_with_price(isin: str, name: str, asset_class: str, dry_run: bool = False) -> AssetResolution:
    """
    Liefert das bestehende Asset zu *isin*, oder legt bei einem neuen Asset nur
    dann eines an, wenn zuvor ein aktueller Kurs erfolgreich abgerufen wurde.

    - Asset existiert bereits: wird unverändert zurückgegeben (kein Kurs-Abruf).
    - Asset ist neu und Kurs-Abruf schlägt fehl: asset=None, error gesetzt,
      es wird NICHTS in der DB angelegt.
    - Asset ist neu, Kurs-Abruf erfolgreich, dry_run=True: nichts wird
      gespeichert, aber created=True und price sind gesetzt (Vorschau).
    - Asset ist neu, Kurs-Abruf erfolgreich, dry_run=False: Asset + Price
      werden angelegt.
    """
    existing = Asset.objects.filter(isin=isin).first()
    if existing:
        return AssetResolution(existing, False, existing.current_price, None)

    try:
        price = _provider_manager.isin2price(isin, asset_class)
    except Exception as exc:
        logger.warning(f"Kurs-Abruf für neues Asset {isin} fehlgeschlagen: {exc}")
        return AssetResolution(None, False, None, f"Kurs-Abruf fehlgeschlagen: {exc}")

    if price is None:
        logger.warning(f"Kurs-Abruf für neues Asset {isin} lieferte keinen Kurs")
        return AssetResolution(None, False, None, "Kein Kurs verfügbar (alle Kursquellen fehlgeschlagen)")

    if dry_run:
        return AssetResolution(None, True, price, None)

    with transaction.atomic():
        asset = Asset.objects.create(isin=isin, name=name, asset_class=asset_class)
        Price.objects.create(asset=asset, current_price=price, timestamp=timezone.now())
    asset.refresh_from_db()
    logger.info(f"Neues Asset angelegt: {isin} ({name}) @ {price}")
    return AssetResolution(asset, True, asset.current_price, None)


def refresh_asset_price(asset: Asset, failures: Optional[list] = None) -> Optional[Decimal]:
    """Holt aktiv den aktuellen Kurs für ein bestehendes Asset und speichert ihn.

    Ist asset.price_fetch_blocked gesetzt, wird gar nicht erst versucht. Schlägt der
    Abruf fehl, wird das Flag gesetzt (siehe flag_price_fetch_failure) und — falls
    *failures* übergeben wurde — ein Eintrag angehängt, den der Aufrufer am Ende
    seines Laufs gebündelt per report_price_fetch_failures() meldet.

    Gibt den neuen Kurs zurück, oder None (blockiert oder Fehler).
    """
    if asset.price_fetch_blocked:
        logger.info(f"Kurs-Abruf für {asset.isin} übersprungen (price_fetch_blocked=True)")
        return None

    try:
        price = _provider_manager.isin2price(asset.isin, asset.asset_class, yahoo_symbol=asset.yahoo_symbol)
    except Exception as exc:
        logger.warning(f"Kurs-Abruf für {asset.isin} fehlgeschlagen: {exc}")
        escalated = flag_price_fetch_failure(asset, str(exc))
        if escalated and failures is not None:
            failures.append(_failure_entry(asset, str(exc)))
        return None

    if price is None:
        error_detail = "Alle Kursquellen lieferten keinen Preis (isin2price → None)."
        logger.warning(f"Kurs-Abruf für {asset.isin} lieferte keinen Kurs")
        escalated = flag_price_fetch_failure(asset, error_detail)
        if escalated and failures is not None:
            failures.append(_failure_entry(asset, error_detail))
        return None

    Price.objects.create(asset=asset, current_price=price, timestamp=timezone.now())
    clear_price_fetch_failure(asset)
    if asset.suspicious_price is not None:
        asset.suspicious_price = None
        asset.suspicious_price_since = None
        asset.save(update_fields=["suspicious_price", "suspicious_price_since"])
    return price


def flag_price_fetch_failure(asset: Asset, error_detail: str) -> bool:
    """
    Registriert einen fehlgeschlagenen Kurs-Abruf für *asset*.

    Beim ersten Fehlschlag wird nur price_fetch_failing_since gesetzt — noch KEIN
    price_fetch_blocked, noch kein Ticket. Erst wenn seit diesem ersten Fehlschlag
    mehr als PRICE_FETCH_FAILURE_THRESHOLD vergangen ist, wird price_fetch_blocked
    gesetzt. Legt selbst KEIN Jira-Ticket an — der Aufrufer sammelt die eskalierten
    Fehler über einen ganzen Lauf hinweg und meldet sie gebündelt über
    report_price_fetch_failures(), damit ein zentraler Ausfall (z. B. Comdirect
    nicht erreichbar) nicht ein Ticket pro betroffenem Asset erzeugt.

    Solange price_fetch_blocked gesetzt bleibt, überspringen refresh_asset_price()
    und update_prices weitere Abrufversuche für dieses Asset.

    Gibt True zurück, wenn das Asset durch diesen Aufruf gerade neu blockiert
    wurde (Signal für den Aufrufer, es fürs Jira-Ticket zu melden).
    """
    now = timezone.now()

    if asset.price_fetch_failing_since is None:
        asset.price_fetch_failing_since = now
        asset.save(update_fields=["price_fetch_failing_since"])
        logger.info(
            f"Kurs-Abruf für {asset.isin} fehlgeschlagen (erster Fehlschlag, "
            f"noch nicht blockiert): {error_detail}"
        )
        return False

    if asset.price_fetch_blocked:
        return False

    if now - asset.price_fetch_failing_since >= PRICE_FETCH_FAILURE_THRESHOLD:
        asset.price_fetch_blocked = True
        asset.save(update_fields=["price_fetch_blocked"])
        logger.warning(
            f"Kurs-Abruf für {asset.isin} schlägt seit über 24h fehl — "
            f"price_fetch_blocked gesetzt: {error_detail}"
        )
        return True

    return False


def clear_price_fetch_failure(asset: Asset) -> None:
    """Setzt price_fetch_failing_since nach einem erfolgreichen Kurs-Abruf zurück."""
    if asset.price_fetch_failing_since is not None:
        asset.price_fetch_failing_since = None
        asset.save(update_fields=["price_fetch_failing_since"])


def _failure_entry(asset: Asset, error_detail: str) -> dict:
    return {
        "isin": asset.isin,
        "name": asset.name,
        "asset_class": asset.asset_class,
        "error": error_detail,
    }


def report_price_fetch_failures(failures: list) -> None:
    """
    Legt EIN Jira-Bug-Ticket an, das alle in einem Lauf fehlgeschlagenen
    Kurs-Abrufe auflistet (statt eines Tickets pro Asset). No-op bei leerer Liste.

    failures: Liste von dicts {"isin", "name", "asset_class", "error"}
    (siehe _failure_entry).
    """
    if not failures:
        return

    lines = "\n".join(
        f"- {f['name']} ({f['isin']}, {f['asset_class']}): {f['error']}"
        for f in failures
    )
    try:
        JiraClient().create_issue(
            summary=f"Kurs-Abruf fehlgeschlagen für {len(failures)} Asset(s)",
            description=(
                f"Für folgende {len(failures)} Asset(s) konnte kein aktueller Kurs "
                f"ermittelt werden:\n\n{lines}\n\n"
                f"Zeitpunkt: {timezone.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                f"price_fetch_blocked wurde für alle betroffenen Assets automatisch auf "
                f"True gesetzt — weitere automatische Abrufversuche sind pausiert, bis das "
                f"Feld manuell wieder auf False gesetzt wird (Django-Admin oder "
                f"/fintech/clean_up/ → Remove Price Fetch Blocker)."
            ),
            issue_type="Bug",
        )
        logger.info(f"Sammel-Jira-Ticket für {len(failures)} fehlgeschlagene Kurs-Abrufe angelegt.")
    except JiraApiError as exc:
        logger.error(
            f"Sammel-Jira-Ticket für {len(failures)} fehlgeschlagene Kurs-Abrufe "
            f"konnte nicht angelegt werden: {exc}"
        )


def compute_stock_lookthrough_rows() -> list[dict]:
    """
    Aktien-Look-Through: eine Zeile pro Aktie (direkt gehalten und/oder über
    Fonds/ETFs gehalten via FondHolding-Mapping), mit direktem + über Fonds
    gehaltenem Anteil. Extrahiert aus views.portfolio_overall_stocks, damit
    dieselbe Logik auch für die Auswahl der News-Zielunternehmen
    (management-Command update_news) genutzt werden kann.

    Kategorie-Herkunft je Aktie (erste zutreffende Regel):
      1. Holdings.category der Aktie selbst (falls direkt gehalten).
      2. Holdings.category des Fonds mit dem höchsten Gewicht für diese Aktie.
      3. 'Sonstiges'.

    Rückgabe: Liste von dicts (row_key, name, isin, symbol, asset_class, logo,
    holdings_id, category, value_stock, value_fund, value_total,
    fund_breakdown), absteigend nach value_total sortiert.
    """
    # Direkter Aktienwert + Holdings-Objekt + Kategorie je Asset (nur STOCK-Holdings)
    direct_value = {}
    holdings_by_isin = {}   # isin -> Holdings (nur direkt gehaltene Aktien; für Edit-Link)
    holding_category = {}   # isin (Aktie ODER Fonds) -> Holdings.category
    stock_holdings = Holdings.objects.select_related('asset').filter(
        asset__asset_class=AssetClass.STOCK, quantity__gt=0,
    )
    for h in stock_holdings:
        price = h.asset.current_price or Decimal('0')
        direct_value[h.asset_id] = h.quantity * price
        holdings_by_isin[h.asset_id] = h
        holding_category[h.asset_id] = h.category

    # Aktueller Wert + Kategorie je gehaltenem Fonds/ETF
    fund_value = {}
    fund_holdings = Holdings.objects.select_related('asset').filter(
        asset__asset_class__in=[AssetClass.ETF, AssetClass.FOND], quantity__gt=0,
    )
    for h in fund_holdings:
        price = h.asset.current_price or Decimal('0')
        fund_value[h.asset_id] = h.quantity * price
        holding_category[h.asset_id] = h.category

    # Fonds mit manuell gepflegten Holdings (ManualFondHolding) haben Vorrang:
    # für diese Fonds wird FondHolding komplett ignoriert.
    manual_override_fund_ids = set(
        ManualFondHolding.objects.filter(fund_id__in=fund_value.keys())
        .values_list('fund_id', flat=True).distinct()
    ) if fund_value else set()

    # Fonds-Wert über FondHolding-Mapping (bzw. ManualFondHolding für Fonds mit
    # Vorrang) auf Aktien verteilen; je Aktie den Fonds mit dem höchsten
    # Gewicht merken (Fallback-Kategorie-Quelle) und das Aktien-Asset selbst
    # (für Aktien ohne eigene Holdings-Zeile).
    look_through_value = {}
    fund_breakdown = {}        # Stock-Key -> Liste der einzelnen Fonds-Beiträge (für Detail-Overlay)
    best_fund_for_stock = {}   # Stock-Key -> (percentage, Fonds-ISIN)
    holding_assets = {}        # Stock-Key -> Asset (nur für reine Look-Through-Aktien nötig)
    virtual_stock_names = {}   # Stock-Key -> Name (manuell erfasste Position ohne Asset-Match)

    def _record_contribution(stock_key, fund, fund_val, percentage, asset=None):
        contribution = fund_val * (percentage / Decimal('100'))
        look_through_value[stock_key] = look_through_value.get(stock_key, Decimal('0')) + contribution
        if asset is not None:
            holding_assets[stock_key] = asset
        fund_breakdown.setdefault(stock_key, []).append({
            'fund_name':    fund.name,
            'fund_isin':    fund.isin,
            'percentage':   percentage,
            'fund_value':   fund_val,
            'contribution': contribution,
        })
        current_best = best_fund_for_stock.get(stock_key)
        if current_best is None or percentage > current_best[0]:
            best_fund_for_stock[stock_key] = (percentage, fund.isin)

    if fund_value:
        auto_fund_ids = set(fund_value.keys()) - manual_override_fund_ids
        mappings = FondHolding.objects.select_related('holding', 'fund').filter(fund_id__in=auto_fund_ids)
        for m in mappings:
            fund_val = fund_value.get(m.fund_id, Decimal('0'))
            _record_contribution(m.holding_id, m.fund, fund_val, m.percentage, asset=m.holding)

    if manual_override_fund_ids:
        # Namensabgleich-Basis: ALLE STOCK-Assets — nicht nur mit Holdings-
        # Zeile, dieselbe Logik wie update_etf_holdings' DAX-/MSCI-World-
        # Tail-Erweiterung (siehe dort für die Begründung).
        known_stock_assets = list(Asset.objects.filter(asset_class=AssetClass.STOCK))
        aliases = load_aliases()
        manual_entries = ManualFondHolding.objects.select_related('fund').filter(
            fund_id__in=manual_override_fund_ids
        )
        for entry in manual_entries:
            fund_val = fund_value.get(entry.fund_id, Decimal('0'))
            matched_asset = match_held_stock(entry.holding_name, known_stock_assets, aliases)
            if matched_asset is not None:
                _record_contribution(matched_asset.isin, entry.fund, fund_val, entry.percentage, asset=matched_asset)
            else:
                stock_key = f"manual-{slugify(entry.fund_id)}-{slugify(entry.holding_name)}"
                virtual_stock_names[stock_key] = entry.holding_name
                _record_contribution(stock_key, entry.fund, fund_val, entry.percentage)

    for breakdown in fund_breakdown.values():
        breakdown.sort(key=lambda d: d['contribution'], reverse=True)

    def resolve_category(stock_key):
        cat = holding_category.get(stock_key)
        if cat:
            return cat
        best = best_fund_for_stock.get(stock_key)
        if best:
            return holding_category.get(best[1])
        return None

    # Je Aktie (oder manuell erfasster Position ohne Asset-Match) eine Zeile
    all_keys = set(direct_value) | set(look_through_value)
    rows = []
    for key in all_keys:
        h = holdings_by_isin.get(key)
        asset = h.asset if h else holding_assets.get(key)
        virtual_name = virtual_stock_names.get(key)
        if asset is None and virtual_name is None:
            continue

        value_stock = direct_value.get(key, Decimal('0'))
        value_fund  = look_through_value.get(key, Decimal('0'))
        cat = resolve_category(key)

        rows.append({
            'row_key':     key,
            'name':        asset.name if asset else virtual_name,
            'isin':        asset.isin if asset else '',
            'symbol':      asset.symbol if asset and asset.symbol else '',
            'asset_class': asset.asset_class if asset else AssetClass.STOCK,
            'logo':        asset.logo if asset and asset.logo else '',
            'holdings_id': h.pk if h else None,
            'category':    CategoryClass(cat).label if cat else 'Sonstiges',
            'value_stock': value_stock,
            'value_fund':  value_fund,
            'value_total': value_stock + value_fund,
            'fund_breakdown': fund_breakdown.get(key, []),
        })
    rows.sort(key=lambda r: r['value_total'], reverse=True)
    return rows


def get_news_target_rows(min_value: Decimal) -> list[dict]:
    """Look-Through-Zeilen (siehe compute_stock_lookthrough_rows) mit
    value_total > min_value — Basis für die News-Feed-Auswahl (update_news)."""
    return [r for r in compute_stock_lookthrough_rows() if r['value_total'] > min_value]
