"""
ISIN-Wechsel eines Assets (z.B. 1:1-Umtausch in neue Aktien).

Die ISIN ist der Primärschlüssel von Asset — ein einfaches Umbenennen geht
deshalb nicht. change_isin() legt das Asset unter der neuen ISIN als Kopie an,
hängt alle abhängigen Zeilen (Holdings, Kurse, Watchlist-Einträge, Alarme, …)
um und löscht das alte Asset. Alles in einer Transaktion; ein Dry-Run führt
dieselben Schritte aus und rollt sie am Ende zurück.

refresh_attributes() setzt danach die Attribute neu, die an der ISIN hängen
(WKN, TradingView-Symbol, Yahoo-Symbol, Kurs) — soweit das automatisch geht.

Genutzt vom Management-Command change_isin und von der Seite
/fintech/isin-change/.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from django.apps import apps
from django.db import transaction

from .models import Asset

logger = logging.getLogger(__name__)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")

# Felder, die beim Kopieren nicht übernommen werden: Sie beschreiben den
# (meist schon fehlschlagenden) Kurs-Abruf unter der ALTEN ISIN.
_RESET_FIELDS = {
    "price_fetch_blocked": False,
    "price_fetch_failing_since": None,
    "suspicious_price": None,
    "suspicious_price_since": None,
}

OK = "ok"            # automatisch neu gesetzt
UNCHANGED = "same"   # unverändert übernommen, passt
MANUAL = "manual"    # konnte nicht automatisch geklärt werden


class IsinChangeError(Exception):
    """Fachlicher Fehler — es wurde nichts geändert."""


@dataclass
class IsinChangeResult:
    old_isin: str
    new_isin: str
    name: str
    dry_run: bool
    moved: list = field(default_factory=list)   # [{'label', 'count'}], nur Tabellen mit Zeilen

    @property
    def total_moved(self) -> int:
        return sum(row["count"] for row in self.moved)


@dataclass
class AttributeResult:
    label: str
    old: str
    new: str
    status: str
    note: str = ""


def normalize_isin(value: str) -> str:
    return (value or "").strip().upper()


def derive_wkn(isin: str) -> Optional[str]:
    """Bei deutschen ISINs steckt die WKN in den Stellen 6–11 (DE000PFSE253 → PFSE25)."""
    if isin.startswith("DE") and len(isin) == 12:
        return isin[5:11]
    return None


def _asset_references():
    """Alle (Model, Feld), die per FK/OneToOne auf Asset zeigen — inklusive der
    automatisch erzeugten M2M-Zwischentabellen und des Selbstbezugs
    Asset.holdings_reference. Neue Relationen sind damit automatisch dabei."""
    for model in apps.get_models(include_auto_created=True):
        if not model._meta.managed or model._meta.proxy:
            continue
        for f in model._meta.local_concrete_fields:
            if f.remote_field and f.remote_field.model is Asset:
                yield model, f


def _reference_label(model, f) -> str:
    label = str(model._meta.verbose_name_plural if not model._meta.auto_created else model._meta.db_table)
    # Feldname nur nennen, wo er etwas aussagt (FondHolding.fund vs. .holding)
    return label if f.name == "asset" else f"{label} ({f.name})"


def change_isin(old_isin: str, new_isin: str, dry_run: bool = False) -> IsinChangeResult:
    """Zieht ein Asset von *old_isin* auf *new_isin* um.

    Wirft IsinChangeError, wenn die Eingaben nicht passen (dann ist nichts
    geändert). Bei dry_run=True wird alles ausgeführt und zurückgerollt.
    """
    old_isin, new_isin = normalize_isin(old_isin), normalize_isin(new_isin)
    for label, value in (("Alte", old_isin), ("Neue", new_isin)):
        if not ISIN_RE.match(value):
            raise IsinChangeError(f"{label} ISIN '{value}' ist keine gültige ISIN (12 Zeichen, 2 Buchstaben am Anfang).")
    if old_isin == new_isin:
        raise IsinChangeError("Alte und neue ISIN sind identisch.")

    with transaction.atomic():
        old = Asset.objects.select_for_update().filter(pk=old_isin).first()
        if old is None:
            raise IsinChangeError(f"Kein Asset mit der ISIN {old_isin} gefunden.")
        if Asset.objects.filter(pk=new_isin).exists():
            raise IsinChangeError(
                f"Es gibt bereits ein Asset mit der ISIN {new_isin}. Zusammenführen zweier "
                f"bestehender Assets wird nicht unterstützt."
            )

        result = IsinChangeResult(old_isin=old_isin, new_isin=new_isin, name=old.name, dry_run=dry_run)

        # 1. Kopie unter neuer ISIN anlegen. Die WKN ist unique und gehört zur
        #    alten ISIN — sie wird hier geleert und von refresh_attributes()
        #    neu gesetzt.
        values = {
            f.attname: getattr(old, f.attname)
            for f in Asset._meta.concrete_fields
            if not f.primary_key
        }
        values.update(_RESET_FIELDS)
        values["wkn"] = None
        if values.get("holdings_reference_id") == old_isin:
            values["holdings_reference_id"] = new_isin
        Asset.objects.filter(pk=old_isin).update(wkn=None)
        Asset(isin=new_isin, **values).save(force_insert=True)
        # auto_now_add/auto_now überschreiben die kopierten Zeitstempel beim Insert
        Asset.objects.filter(pk=new_isin).update(created_at=old.created_at)

        # 2. Abhängige Zeilen umhängen. update() statt save(): keine Seiteneffekte
        #    (Price.save() würde z.B. Alarme prüfen).
        for model, f in _asset_references():
            count = model._base_manager.filter(**{f.attname: old_isin}).update(**{f.attname: new_isin})
            if count:
                result.moved.append({"label": _reference_label(model, f), "count": count})

        # 3. Altes Asset löschen. Hängt wider Erwarten noch etwas daran, würde
        #    die Cascade es mitlöschen — dann lieber abbrechen.
        _, deleted = Asset.objects.get(pk=old_isin).delete()
        extra = {name: n for name, n in deleted.items() if n and name != Asset._meta.label}
        if extra:
            raise IsinChangeError(f"Abbruch: am alten Asset hingen noch Daten, die gelöscht worden wären: {extra}")

        if dry_run:
            transaction.set_rollback(True)

    logger.info(
        f"ISIN-Wechsel {'(Dry-Run) ' if dry_run else ''}{old_isin} → {new_isin} ({result.name}): "
        f"{result.total_moved} Zeilen umgehängt"
    )
    return result


def refresh_attributes(old_isin: str, new_isin: str, dry_run: bool = False) -> list:
    """Setzt WKN, TradingView-Symbol, Yahoo-Symbol und Kurs für die neue ISIN.

    Nach einem echten Lauf wird das Asset unter *new_isin* aktualisiert. Im
    Dry-Run existiert es noch unter *old_isin*; dann wird nur ermittelt und
    nichts gespeichert. Einträge mit status == MANUAL muss der Anwender im
    Admin (Change Asset) prüfen.
    """
    old_isin, new_isin = normalize_isin(old_isin), normalize_isin(new_isin)
    asset = Asset.objects.get(pk=old_isin if dry_run else new_isin)
    results = []
    update = {}

    # --- WKN -----------------------------------------------------------
    wkn = derive_wkn(new_isin)
    wkn_note = "aus der deutschen ISIN abgeleitet"
    if not wkn:
        wkn = _lookup_wkn(new_isin, asset.asset_class)
        wkn_note = "von Comdirect/JustETF/AlleAktien"
    if wkn and Asset.objects.filter(wkn=wkn).exclude(pk=asset.pk).exists():
        results.append(AttributeResult("WKN", asset.wkn or "", "", MANUAL, f"{wkn} ist bereits einem anderen Asset zugeordnet"))
    elif wkn:
        update["wkn"] = wkn
        results.append(AttributeResult("WKN", asset.wkn or "", wkn, OK, wkn_note))
    else:
        results.append(AttributeResult("WKN", asset.wkn or "", "", MANUAL, "keine WKN gefunden — bitte im Admin eintragen"))

    # --- TradingView-Symbol ---------------------------------------------
    symbol = _lookup_tradingview_symbol(new_isin)
    if symbol:
        update["symbol"] = symbol
        status = UNCHANGED if symbol == asset.symbol else OK
        results.append(AttributeResult("Symbol (TradingView)", asset.symbol or "", symbol, status, "von OpenFIGI"))
    elif asset.symbol:
        results.append(AttributeResult(
            "Symbol (TradingView)", asset.symbol, asset.symbol, MANUAL,
            "OpenFIGI kennt die neue ISIN noch nicht — altes Symbol übernommen, bitte prüfen",
        ))
    else:
        results.append(AttributeResult("Symbol (TradingView)", "", "", MANUAL, "kein Symbol gefunden — bitte im Admin eintragen"))

    # --- Yahoo-Symbol ---------------------------------------------------
    # yahoo_symbol ist nur ein Override für den Fall, dass Yahoos ISIN-Suche
    # nichts findet. Findet Yahoo die neue ISIN, bleibt das Feld wie es ist.
    yahoo_new = _lookup_yahoo_symbol(new_isin)
    current = asset.yahoo_symbol or ""
    if yahoo_new:
        note = f"Yahoo findet die neue ISIN ({yahoo_new})"
        if current and current != yahoo_new:
            results.append(AttributeResult("Yahoo-Symbol", current, current, MANUAL, f"{note}, der manuelle Override lautet aber {current} — bitte prüfen"))
        else:
            results.append(AttributeResult("Yahoo-Symbol", current, current, UNCHANGED, f"{note}, kein Override nötig"))
    elif current:
        results.append(AttributeResult("Yahoo-Symbol", current, current, MANUAL, "Yahoo findet die neue ISIN noch nicht — bestehender Override übernommen, bitte prüfen"))
    else:
        yahoo_old = _lookup_yahoo_symbol(old_isin)
        if yahoo_old:
            update["yahoo_symbol"] = yahoo_old
            results.append(AttributeResult(
                "Yahoo-Symbol", "", yahoo_old, OK,
                "Yahoo findet die neue ISIN noch nicht — Ticker der alten ISIN als Override gesetzt",
            ))
        else:
            results.append(AttributeResult("Yahoo-Symbol", "", "", MANUAL, "Yahoo findet weder die neue noch die alte ISIN — bitte im Admin eintragen"))

    if update and not dry_run:
        Asset.objects.filter(pk=asset.pk).update(**update)
        asset.refresh_from_db()

    # --- Kurs ------------------------------------------------------------
    results.append(_check_price(asset, new_isin, update.get("yahoo_symbol") or asset.yahoo_symbol, dry_run))
    return results


def needs_manual_review(attributes: list) -> bool:
    return any(a.status == MANUAL for a in attributes)


# ---------------------------------------------------------------------------
# Externe Abfragen — jeweils fehlertolerant, None = nichts gefunden
# ---------------------------------------------------------------------------

def _provider_manager():
    from .services import _provider_manager as pm
    return pm


def _lookup_wkn(isin: str, asset_class: str) -> Optional[str]:
    try:
        return _provider_manager().isin2wkn(isin, asset_class)
    except Exception as exc:
        logger.warning(f"WKN-Suche fehlgeschlagen für {isin}: {exc}")
        return None


def _lookup_tradingview_symbol(isin: str) -> Optional[str]:
    from .apis.services.openfigi import OpenFigiService
    symbol = OpenFigiService().isin2symbol(isin)
    # Gleiche Normalisierung wie beim Auto-Fetch in views.py ("XETR:RHM" → "XETR-RHM")
    return symbol.replace(":", "-").replace(".", "-") if symbol else None


def _lookup_yahoo_symbol(isin: str) -> Optional[str]:
    from .apis.services.yahoo_finance import YahooFinanceRequest
    try:
        return YahooFinanceRequest()._isin2symbol(isin)
    except Exception as exc:
        logger.warning(f"Yahoo-Symbol-Suche fehlgeschlagen für {isin}: {exc}")
        return None


def _check_price(asset: Asset, new_isin: str, yahoo_symbol: Optional[str], dry_run: bool) -> AttributeResult:
    old = f"{asset.current_price:.4f}" if asset.current_price is not None else ""
    try:
        if dry_run:
            price = _provider_manager().isin2price(new_isin, asset.asset_class, yahoo_symbol=yahoo_symbol)
        else:
            from .services import refresh_asset_price
            price = refresh_asset_price(asset)
    except Exception as exc:
        logger.warning(f"Kurs-Abruf für {new_isin} fehlgeschlagen: {exc}")
        price = None
    if price is None:
        return AttributeResult("Kurs", old, old, MANUAL, "unter der neuen ISIN kein Kurs abrufbar — Yahoo-Symbol im Admin prüfen")
    note = "Kurs unter der neuen ISIN abrufbar" if dry_run else "Kurs unter der neuen ISIN abgerufen und gespeichert"
    return AttributeResult("Kurs", old, f"{price:.4f}", OK, note)
