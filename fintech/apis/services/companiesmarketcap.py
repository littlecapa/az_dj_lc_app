"""
Vollständige Holdings-Liste von companiesmarketcap.com — anders als JustETF
(nur Top 10 gratis) liefert diese Seite die komplette Positionsliste statisch
im HTML, allerdings ohne ISIN (nur Name + Ticker). Eignet sich daher nur zum
Ergänzen von Gewichten für Aktien, die im eigenen System bereits über ihre
ISIN bekannt sind (Namensabgleich), nicht zum Neuanlegen.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import List, TypedDict

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MSCI_WORLD_URL = "https://companiesmarketcap.com/ishares-core-msci-world-ucits-etf-usd-acc/holdings/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class RankedHolding(TypedDict):
    name: str
    symbol: str
    percentage: Decimal


def get_holdings(url: str = MSCI_WORLD_URL) -> List[RankedHolding]:
    """Vollständige Holdings-Liste einer companiesmarketcap.com-Fondsseite,
    bereits nach Gewicht absteigend sortiert (so wie die Seite sie liefert)."""
    response = requests.get(url, headers=_HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table", class_="marketcap-table")
    if table is None:
        logger.warning(f"Holdings-Tabelle bei companiesmarketcap.com nicht gefunden: {url}")
        return []

    body = table.find("tbody")
    if body is None:
        return []

    holdings: List[RankedHolding] = []
    for row in body.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        weight_text = cells[0].get_text(strip=True).split("%")[0].strip()
        name = cells[1].get_text(strip=True)
        symbol = cells[2].get_text(strip=True)

        if not name:
            continue
        try:
            percentage = Decimal(weight_text)
        except InvalidOperation:
            continue

        holdings.append({"name": name, "symbol": symbol, "percentage": percentage})

    logger.info(f"companiesmarketcap.com Holdings von {url}: {len(holdings)} Positionen")
    return holdings
