"""
Comdirect Finance Service
=========================
Liefert 52-Wochen-Hoch und -Tief für Wertpapiere via Comdirect Informer.

Funktionsweise
--------------
1. GET https://www.comdirect.de/inf/search/all.html?SEARCH_VALUE={ISIN}
   → Redirect zur Asset-Detailseite (z.B. /inf/aktien/{ISIN})
2. HTML-Parsing: "52W Hoch" und "52W Tief" aus der Kursübersicht extrahieren
3. Aktueller Kurs wird aus "Aktuell" / "Rücknahmepreis" extrahiert

Besonderheiten
--------------
- Liefert EUR-Preise (Xetra/Börse Frankfurt) → kein Currency-Mismatch
- Nur für Aktien verfügbar (Fonds zeigen kein 52W-Range auf Comdirect)
- Kein API-Key, kein OAuth — nur HTML-Scraping
- User-Agent: Browser-ähnlich setzen (sonst 403)
"""

import logging
import re
import requests

from .request_lib import KeyNotFoundWarning

logger = logging.getLogger(__name__)

_SEARCH_URL  = "https://www.comdirect.de/inf/search/all.html?SEARCH_VALUE={isin}"
_AKTIEN_URL  = "https://www.comdirect.de/inf/aktien/{isin}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Dezimal-Zahl im deutschen Format: 1.234,56 oder 234,56
_DE_NUMBER_RE = re.compile(r"[\d]{1,3}(?:\.[\d]{3})*,[\d]+|[\d]+,[\d]+")


def _parse_de_number(text: str):
    """Wandelt deutschen Dezimalstring (z.B. '272,95' oder '1.234,56') in float um."""
    m = _DE_NUMBER_RE.search(text)
    if not m:
        return None
    raw = m.group(0).replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_week52(html: str) :
    """
    Extrahiert 52W-Hoch, 52W-Tief und aktuellen Kurs aus Comdirect-HTML.

    HTML-Struktur (server-side rendered):
        <th ...>52W Hoch</th><td ...>272,95</td>
        <th ...>52W Tief</th><td ...>135,44</td>

    Aktueller Kurs aus Schema.org structured data:
        itemprop="price" content="159.4"
    oder aus Xetra-Kurs-Zeile:
        Xetra, Kurs: 159,40 EUR

    Gibt None zurück wenn keine 52W-Daten gefunden.
    """
    # 52W Hoch/Tief aus Tabellen-HTML
    m_high = re.search(r"52W\s*Hoch</th>\s*<td[^>]*>([\d.,]+)</td>", html)
    m_low  = re.search(r"52W\s*Tief</th>\s*<td[^>]*>([\d.,]+)</td>", html)

    if not m_high or not m_low:
        return None

    high = _parse_de_number(m_high.group(1))
    low  = _parse_de_number(m_low.group(1))

    if high is None or low is None:
        return None

    # Aktueller Kurs: zuerst Schema.org (itemprop price, dot als Dezimal)
    current = None
    m_cur = re.search(r'itemprop="price"\s+content="([\d.]+)"', html)
    if m_cur:
        try:
            current = float(m_cur.group(1))
        except ValueError:
            pass

    # Fallback: Xetra-Kurs aus Beschreibungs-Meta
    if current is None:
        m_xetra = re.search(r"Xetra,\s*Kurs:\s*([\d.,]+)\s*EUR", html)
        if m_xetra:
            current = _parse_de_number(m_xetra.group(1))

    logger.info(f"Comdirect 52W: H={high} L={low} cur={current} EUR")
    return {
        "high":     str(high),
        "low":      str(low),
        "currency": "EUR",
        "current":  str(current) if current is not None else None,
    }


class ComdirectFinanceRequest:
    """Comdirect Informer: 52W-Hoch/Tief per ISIN."""

    def __init__(self):
        self.id = "comdirect_finance"

    def isin2week52(self, isin: str) -> dict:
        """
        Gibt {"high", "low", "currency": "EUR", "current"} zurück.

        Raises KeyNotFoundWarning wenn die ISIN nicht gefunden wird oder
        Comdirect keine 52W-Daten für dieses Instrument anzeigt (z.B. Fonds).
        """
        # Strategie 1: Direkte ISIN-URL für Aktien
        data = self._try_url(_AKTIEN_URL.format(isin=isin), isin)
        if data:
            return data

        # Strategie 2: Suche → Redirect zur richtigen Kategorienseite
        data = self._try_search(isin)
        if data:
            return data

        raise KeyNotFoundWarning(
            f"Comdirect: keine 52W-Daten für {isin} "
            f"(kein Aktien-Listing oder kein 52W-Range auf Comdirect)"
        )

    def _try_url(self, url: str, isin: str) :
        """Ruft URL ab, gibt None bei 404 oder fehlenden 52W-Daten."""
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        except requests.RequestException as exc:
            logger.warning(f"Comdirect request failed for {url}: {exc}")
            return None

        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning(f"Comdirect returned {resp.status_code} for {url}")
            return None

        return _extract_week52(resp.text)

    def _try_search(self, isin: str) :
        """Sucht ISIN über Comdirect-Suche → folgt Redirect → parst 52W-Daten."""
        url = _SEARCH_URL.format(isin=isin)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        except requests.RequestException as exc:
            logger.warning(f"Comdirect search failed for {isin}: {exc}")
            return None

        if resp.status_code != 200:
            return None

        # Nach Redirect auf der Zielseite parsen
        return _extract_week52(resp.text)
