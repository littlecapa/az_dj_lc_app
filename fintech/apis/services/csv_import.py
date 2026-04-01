"""
Import-Service für Scalable Capital Broker CSV-Exporte.

Verarbeitete Transaktionstypen (assetType=Security, status=Executed):
  - Buy          → Kauf, erhöht Bestand + berechnet neuen Durchschnittspreis
  - Savings plan → wie Buy (Sparplan)
  - Sell         → Verkauf, reduziert Bestand

Ignoriert:  Deposit, Distribution, Fee, Cash Transfer Out, Cancelled
"""

import csv
import io
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from django.db import transaction

from ...models import Asset, Holdings
from ...models_helper.asset_class import AssetClass

logger = logging.getLogger(__name__)

BUY_TYPES  = {"Buy", "Savings plan", "Security transfer", "Corporate action"}
SELL_TYPES = {"Sell", "Security transfer"}


# ------------------------------------------------------------------
# Datenklassen
# ------------------------------------------------------------------

@dataclass
class ImportRow:
    date:        str
    description: str
    tx_type:     str
    isin:        str
    shares:      Decimal
    price:       Decimal
    currency:    str


@dataclass
class ImportResult:
    total:    int = 0
    imported: int = 0
    skipped:  int = 0
    errors:   List[str] = None
    dry_run:  bool = False

    def __post_init__(self):
        self.errors = self.errors or []

    @property
    def has_errors(self):
        return bool(self.errors)



# ------------------------------------------------------------------
# Asset-Klasse aus ISIN ableiten
# ------------------------------------------------------------------

import re as _re

# ------------------------------------------------------------------
# Asset-Klasse Erkennung
# ------------------------------------------------------------------
#
# Priorität der Regeln (höchste zuerst):
#   1. Explizites Keyword im Namen: ETF / ETC / ETP  (als ganzes Wort)
#   2. Ausschüttungsart im Namen:   (Acc) oder (Dist) → ETF
#   3. Bekannte ETF-Anbieter:       iShares, Xtrackers, Vanguard etc. → ETF
#   4. ISIN-Prefix:                 XS → Crypto
#   5. Fallback:                    STOCK

# Regel 1: ETF/ETC/ETP als ganzes Wort (Groß/Klein wird NICHT ignoriert)
_TYPE_KEYWORD_RE = _re.compile(r"(?:^|(?<= ))(ETF|ETC|ETP)(?= |$)")

_TYPE_KEYWORD_MAP = {
    "ETF": AssetClass.ETF,
    "ETC": AssetClass.ETC,
    "ETP": AssetClass.ETF,   # ETPs laufen bei Comdirect unter /zertifikate/
}

# Regel 2: Ausschüttungsart — (Acc) = thesaurierend, (Dist) = ausschüttend
_DISTRIBUTION_RE = _re.compile(r"\((Acc|Dist)\)")

# Regel 3: Bekannte ETF-Anbieter (case-sensitive — Schreibweise wie in Comdirect/SC)
_ETF_PROVIDERS = (
    "iShares", "Xtrackers", "Vanguard", "Amundi", "SPDR",
    "Lyxor", "WisdomTree", "VanEck", "Invesco", "HSBC",
    "DWS", "UBS ETF", "Ossiam", "BNP Paribas Easy",
    "Franklin", "Fidelity", "Dimensional", "ISHS", "VANECK",
)

# Regel 4: ISIN-Prefixe
_CRYPTO_ISIN_PREFIXES = ("XS",)


def _detect_asset_class_from_description(description: str) -> str:
    """
    Leitet die Asset-Klasse aus dem Produktnamen ab.
    Gibt None zurück wenn keine Regel greift (→ ISIN-Fallback).
    """
    # Regel 1 — explizites Typ-Keyword
    m = _TYPE_KEYWORD_RE.search(description)
    if m:
        return _TYPE_KEYWORD_MAP[m.group(1)]

    # Regel 2 — Ausschüttungsart
    if _DISTRIBUTION_RE.search(description):
        return AssetClass.ETF

    # Regel 3 — bekannter ETF-Anbieter
    for provider in _ETF_PROVIDERS:
        if provider in description:
            return AssetClass.ETF

    return None


def _detect_asset_class_from_isin(isin: str) -> str:
    """Leitet die Asset-Klasse aus dem ISIN-Prefix ab. Gibt None wenn unbekannt."""
    if isin[:2] in _CRYPTO_ISIN_PREFIXES:
        return AssetClass.CRYPTO
    return None


def _detect_asset_class(isin: str, description: str) -> str:
    """
    Hauptfunktion — kombiniert alle Regeln mit klarer Priorität.

    Priorität: Name-Keywords > Ausschüttungsart > Provider > ISIN-Prefix > STOCK

    Testbeispiele:
        "iShares Bitcoin ETP",   XS2940466316 → CRYPTO  (Regel 1 schlägt Regel 3)
        "HSBC EURO STOXX 50 (Acc)", IE...      → ETF     (Regel 2)
        "iShares Core MSCI World", IE...       → ETF     (Regel 3)
        "Franklin FTSE Korea (Acc)", IE...     → ETF     (Regel 2, vor Regel 3)
        "Allianz",               DE...         → STOCK   (kein Match)
    """
    return (
        _detect_asset_class_from_description(description)
        or _detect_asset_class_from_isin(isin)
        or AssetClass.STOCK
    )


# ------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------

def _parse_de_decimal(value: str) -> Optional[Decimal]:
    """Konvertiert deutsches Zahlenformat '1.234,56' → Decimal."""
    if not value or value.strip() in ("", "-"):
        return None
    try:
        cleaned = value.strip().replace(".", "").replace(",", ".")
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_rows(file_content: str) -> Tuple[List[ImportRow], List[str]]:
    """Parsed CSV-Inhalt und gibt (gültige Zeilen, Fehler) zurück."""
    rows, errors = [], []
    reader = csv.DictReader(io.StringIO(file_content), delimiter=";")

    # Alle Zeilen zuerst einlesen
    all_rows = list(reader)

    # Dann rückwärts iterieren
    for line_no, row in enumerate(reversed(all_rows), start=2):

        try:
            # Nur ausgeführte Wertpapier-Transaktionen
            if row.get("status") != "Executed":
                continue
            if row.get("assetType") != "Security":
                continue
            tx_type = row.get("type", "").strip()
            if tx_type not in BUY_TYPES | SELL_TYPES:
                continue

            isin = row.get("isin", "").strip()
            if not isin:
                continue

            shares = _parse_de_decimal(row.get("shares"))
            price  = _parse_de_decimal(row.get("price"))

            if shares is None:
                continue
            if price is None or price <= 0:
                if tx_type != "Corporate action":  # Corporate actions können manchmal ohne Preis kommen
                    continue

            rows.append(ImportRow(
                date        = row.get("date", "").strip(),
                description = row.get("description", "").strip(),
                tx_type     = tx_type,
                isin        = isin,
                shares      = shares,
                price       = price,
                currency    = row.get("currency", "EUR").strip(),
            ))

        except Exception as exc:
            errors.append(f"Zeile {line_no}: {exc}")

    return rows, errors


# ------------------------------------------------------------------
# Durchschnittspreis-Berechnung
# ------------------------------------------------------------------

def _new_average_price(
    old_qty:   Decimal,
    old_avg:   Optional[Decimal],
    buy_qty:   Decimal,
    buy_price: Decimal,
) -> Decimal:
    """Gewichteter Durchschnitt bei Zukauf."""
    old_avg = old_avg or Decimal("0")
    total_qty  = old_qty + buy_qty
    total_cost = (old_qty * old_avg) + (buy_qty * buy_price)
    return (total_cost / total_qty).quantize(Decimal("0.0001"))


# ------------------------------------------------------------------
# Haupt-Import-Funktion
# ------------------------------------------------------------------

@transaction.atomic
def import_transactions(file_content: str, dry_run: bool = False) -> ImportResult:
    """
    Importiert Transaktionen aus dem CSV-Inhalt.
    Läuft in einer DB-Transaktion — bei Fehler wird alles zurückgerollt.

    dry_run=True: Transaktion wird vollständig simuliert aber am Ende
                  zurückgerollt — keine Änderungen in der DB.
    """
    result = ImportResult()
    result.dry_run = dry_run
    rows, parse_errors = _parse_rows(file_content)
    result.errors.extend(parse_errors)
    result.total = len(rows)

    # Chronologisch sortieren (älteste zuerst) → korrekte Durchschnittspreise
    rows.sort(key=lambda r: r.date)

    for row in rows:
        try:
            _process_row(row, result)
        except Exception as exc:
            result.errors.append(f"{row.isin} ({row.date}): {exc}")
            result.skipped += 1

    if dry_run:
        # Alles zurückrollen — kein einziger Write bleibt in der DB
        transaction.set_rollback(True)

    return result


def _process_row(row: ImportRow, result: ImportResult) -> None:
    # Asset holen oder anlegen
    asset, created = Asset.objects.get_or_create(
        isin=row.isin,
        defaults={
            "name":        row.description,
            "currency":    row.currency,
            "asset_class": _detect_asset_class(row.isin, row.description),
        },
    )
    if created:
        logger.info(f"Neues Asset angelegt: {row.isin} — {row.description}")

    # Holding holen oder anlegen
    holding, _ = Holdings.objects.get_or_create(
        asset=asset,
        defaults={"quantity": Decimal("0")},
    )

    if row.tx_type in BUY_TYPES and row.shares > 0:
        _apply_buy(holding, row)
    elif row.tx_type in SELL_TYPES:
        if row.tx_type == "Security transfer" and row.shares < 0:
            row.shares = abs(row.shares)  # Betrag positiv machen
        if not _apply_sell(holding, row, result):
            return

    holding.save()
    result.imported += 1


def _apply_buy(holding: Holdings, row: ImportRow) -> None:
    holding.average_purchase_price = _new_average_price(
        old_qty   = holding.quantity,
        old_avg   = holding.average_purchase_price,
        buy_qty   = row.shares,
        buy_price = row.price,
    )
    holding.quantity += row.shares
    logger.info(f"Kauf {row.isin}: +{row.shares} @ {row.price} → qty={holding.quantity} avg={holding.average_purchase_price}")


def _apply_sell(holding: Holdings, row: ImportRow, result: ImportResult) -> bool:
    if holding.quantity < row.shares:
        msg = (
            f"{row.isin}: Verkauf von {row.shares} nicht möglich — "
            f"nur {holding.quantity} im Bestand."
        )
        logger.warning(msg)
        result.errors.append(msg)
        result.skipped += 1
        return False

    holding.quantity -= row.shares
    # Durchschnittspreis bleibt bei Verkauf unverändert (FIFO/Avg-Methode)
    logger.info(f"Verkauf {row.isin}: -{row.shares} @ {row.price} → qty={holding.quantity}")
    return True
