"""
DAX-Zusammensetzung von Wikipedia (https://de.wikipedia.org/wiki/DAX),
Tabelle "Zusammensetzung" — liefert alle ~40 Positionen mit Name, Symbol
(Xetra-Kürzel) und Indexgewicht in %.

Wikipedia führt keine ISIN in dieser Tabelle, nur Name + Kürzel. Diese
Quelle eignet sich daher NICHT zum Neuanlegen von Assets, sondern nur zum
Ergänzen von Gewichten für Aktien, die im eigenen System bereits über ihre
ISIN bekannt sind (Namensabgleich).
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import List, TypedDict

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DAX_WIKIPEDIA_URL = "https://de.wikipedia.org/wiki/DAX"

_HEADERS = {
    "User-Agent": "az-dj-lc-app/1.0 (persönlicher Portfolio-Tracker; littlecapa)"
}


class DaxConstituent(TypedDict):
    name: str
    symbol: str
    percentage: Decimal


def get_dax_constituents() -> List[DaxConstituent]:
    """Alle DAX-Positionen mit Gewicht, absteigend nach Indexgewicht sortiert.

    Einträge ohne (noch) veröffentlichtes Gewicht (z.B. frisch aufgenommene
    Werte) werden übersprungen statt geraten.
    """
    response = requests.get(DAX_WIKIPEDIA_URL, headers=_HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table", attrs={"data-x-id": "Zusammensetzung"})
    if table is None:
        logger.warning("DAX-Zusammensetzungstabelle bei Wikipedia nicht gefunden")
        return []

    constituents: List[DaxConstituent] = []
    rows = table.find_all("tr")[1:]  # erste Zeile ist der Tabellen-Header
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue

        name = cells[0].get_text(strip=True)
        symbol = cells[1].get_text(strip=True)
        weight_text = cells[4].get_text(strip=True).replace("%", "").replace(",", ".").strip()

        if not name or not symbol:
            continue
        try:
            percentage = Decimal(weight_text)
        except InvalidOperation:
            logger.info(f"DAX-Wert ohne Gewichtsangabe übersprungen: {name} ({symbol})")
            continue

        constituents.append({"name": name, "symbol": symbol, "percentage": percentage})

    constituents.sort(key=lambda c: c["percentage"], reverse=True)
    logger.info(f"DAX-Zusammensetzung von Wikipedia: {len(constituents)} Positionen mit Gewicht")
    return constituents
