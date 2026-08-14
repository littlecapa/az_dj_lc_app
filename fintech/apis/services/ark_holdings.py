"""
Vollständige, tagesaktuelle Holdings-Liste eines ARK-ETFs — direkt von ARK
Invest selbst (öffentliches CSV, täglich aktualisiert). Anders als JustETF
(nur Top 10 gratis) oder Wikipedia/companiesmarketcap.com (keine ISIN)
liefert diese Quelle ALLE Positionen inkl. CUSIP, woraus sich die ISIN
direkt berechnen lässt (ISO 6166) — kein fehleranfälliger Namensabgleich
nötig, echtes Get-or-create per ISIN wie bei JustETF.

Cash-/Geldmarkt-Positionen (z.B. "GOLDMAN FS TRSY OBLIG") und private/nicht
börsennotierte Beteiligungen (z.B. Pre-IPO-Anteile) haben in ARKs CSV kein
Ticker-Kürzel und werden daher übersprungen.
"""
import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import List, TypedDict

import requests

logger = logging.getLogger(__name__)

ARK_CSV_URLS = {
    "ARKK": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    "ARKW": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    "ARKQ": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_AUTONOMOUS_TECH._&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
    "ARKG": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
    "ARKF": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class ArkHolding(TypedDict):
    isin: str
    name: str
    symbol: str
    percentage: Decimal


def cusip_to_isin(cusip: str, country: str = "US") -> str:
    """CUSIP -> ISIN nach ISO 6166: Länderpräfix + CUSIP, Buchstaben als
    Ziffern (A=10..Z=35), Prüfziffer per Luhn-Algorithmus über den
    resultierenden Zifferstring (von rechts beginnend verdoppelt)."""
    payload = (country + cusip).upper()
    digits = "".join(
        ch if ch.isdigit() else str(ord(ch) - ord("A") + 10)
        for ch in payload
    )
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check_digit = (10 - (total % 10)) % 10
    return f"{payload}{check_digit}"


def get_holdings(fund_ticker: str) -> List[ArkHolding]:
    """Vollständige Holdings-Liste eines ARK-ETFs, so wie ARK sie liefert
    (nach Gewicht absteigend sortiert). Wirft ValueError bei unbekanntem
    Ticker, requests.HTTPError bei Abruf-Fehlern."""
    url = ARK_CSV_URLS.get(fund_ticker.upper())
    if not url:
        raise ValueError(f"Kein ARK-CSV-Feed für Ticker '{fund_ticker}' bekannt.")

    response = requests.get(url, headers=_HEADERS, timeout=20)
    response.raise_for_status()

    reader = csv.DictReader(io.StringIO(response.text))
    holdings: List[ArkHolding] = []
    for row in reader:
        ticker = (row.get("ticker") or "").strip()
        cusip = (row.get("cusip") or "").strip()
        name = (row.get("company") or "").strip()
        weight_text = (row.get("weight (%)") or "").replace("%", "").strip()

        # Kein Ticker = Cash-/Geldmarkt-Sweep oder private/nicht börsen-
        # notierte Beteiligung (z.B. Pre-IPO) — keine echte, handelbare Aktie.
        if not ticker or not name or len(cusip) != 9:
            continue
        try:
            percentage = Decimal(weight_text)
        except InvalidOperation:
            continue

        holdings.append({
            "isin": cusip_to_isin(cusip),
            "name": name,
            "symbol": ticker,
            "percentage": percentage,
        })

    logger.info(f"ARK-CSV-Holdings für {fund_ticker}: {len(holdings)} Positionen")
    return holdings
