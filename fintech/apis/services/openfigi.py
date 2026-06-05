"""
OpenFIGI service — ISIN → TradingView-kompatibles Symbol.

API: https://www.openfigi.com/api
- Kostenlos, kein API-Key für Basic-Nutzung (25 req/min)
- POST https://api.openfigi.com/v3/mapping
- Body: [{"idType": "ID_ISIN", "idValue": "<ISIN>"}, ...]
- Max 100 ISINs pro Request

Rückgabe: TradingView-Symbol, z.B. "XETR:RHM", "BME:IBE", "NASDAQ:AAPL"
"""

import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"

# OpenFIGI exchCode → TradingView Exchange-Prefix
EXCHCODE_TO_TV: dict[str, str] = {
    'GY': 'XETR',      # Deutschland XETRA
    'GF': 'FWB',       # Frankfurt
    'FP': 'EURONEXT',  # Frankreich (Paris)
    'SM': 'BME',       # Spanien (Madrid)
    'LN': 'LSE',       # London
    'NO': 'OSL',       # Norwegen (Oslo)
    'AU': 'ASX',       # Australien
    'JT': 'TSE',       # Japan (Tokio)
    'SW': 'SWX',       # Schweiz
    'DC': 'CPH',       # Dänemark (Kopenhagen)
    'NA': 'AMS',       # Niederlande (Amsterdam)
    'BB': 'EBR',       # Belgien (Brüssel)
    'IT': 'MIL',       # Italien (Mailand)
    'UW': 'NASDAQ',    # NASDAQ
    'UN': 'NYSE',      # NYSE
    'UA': 'AMEX',      # AMEX
    'US': 'NASDAQ',    # US-Fallback → NASDAQ
    'KS': 'KRX',       # Korea
    'HK': 'HKEX',      # Hongkong
}

# ISIN-Länderkürzel → bevorzugter OpenFIGI exchCode
ISIN_COUNTRY_PREF: dict = {
    'DE': 'GY',
    'NL': 'NA',
    'FR': 'FP',
    'ES': 'SM',
    'GB': 'LN',
    'NO': 'NO',
    'AU': 'AU',
    'JP': 'JT',
    'CH': 'SW',
    'DK': 'DC',
    'LU': 'GY',   # Luxemburg-Fonds oft auf XETRA
    'IE': 'LN',   # Irische ISIN oft auf LSE
    'US': None,   # US: NASDAQ > NYSE
}


class OpenFigiService:

    def isin2symbol(self, isin: str) -> Optional[str]:
        """Gibt TradingView-Symbol für eine ISIN zurück, oder None."""
        try:
            results = self._query([isin])
            candidates = results[0] if results else []
            return self._best_symbol(isin, candidates)
        except Exception as exc:
            logger.error(f"OpenFIGI isin2symbol({isin}): {exc}")
            return None

    def isin2symbol_batch(self, isins: list) -> dict:
        """
        Gibt {isin: symbol_or_None} für eine Liste von ISINs zurück.
        Maximal 100 ISINs pro Aufruf (OpenFIGI-Limit).
        """
        if not isins:
            return {}
        try:
            results = self._query(isins[:100])
            return {
                isin: self._best_symbol(isin, candidates)
                for isin, candidates in zip(isins, results)
            }
        except Exception as exc:
            logger.error(f"OpenFIGI batch({len(isins)} ISINs): {exc}")
            return {}

    # ── Interne Methoden ──────────────────────────────────────────────────

    def _query(self, isins: list) -> list:
        """Ruft OpenFIGI API ab. Gibt Liste von Kandidaten-Listen zurück."""
        payload = [{"idType": "ID_ISIN", "idValue": isin} for isin in isins]
        resp = requests.post(
            OPENFIGI_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 429:
            logger.warning("OpenFIGI: Rate-Limit erreicht (429)")
            return [[] for _ in isins]
        resp.raise_for_status()

        data = resp.json()
        return [item.get("data", []) for item in data]

    def _best_symbol(self, isin: str, candidates: list) -> Optional[str]:
        """Wählt bestes TradingView-Symbol aus den OpenFIGI-Ergebnissen."""
        if not candidates:
            logger.info(f"OpenFIGI: keine Ergebnisse für {isin}")
            return None

        country = isin[:2].upper()

        # Nur Aktien/Equities berücksichtigen
        equities = [c for c in candidates if c.get('marketSector') == 'Equity']
        pool = equities if equities else candidates

        # Bevorzugter Exchange für dieses Land
        pref = ISIN_COUNTRY_PREF.get(country)
        if pref:
            match = next((c for c in pool if c.get('exchCode') == pref), None)
            if match:
                return self._build(match)

        # US: NASDAQ > NYSE > sonstiges US
        if country == 'US':
            for code in ('UW', 'UN', 'US'):
                match = next((c for c in pool if c.get('exchCode') == code), None)
                if match:
                    return self._build(match)

        # Fallback: erster Equity-Eintrag
        result = self._build(pool[0])
        if result:
            logger.info(f"OpenFIGI: Fallback-Symbol für {isin}: {result}")
        return result

    def _build(self, candidate: dict) -> Optional[str]:
        """Baut 'EXCHANGE:TICKER' aus einem OpenFIGI-Kandidaten."""
        ticker = candidate.get('ticker')
        exch   = candidate.get('exchCode')
        if not ticker:
            return None
        tv_prefix = EXCHCODE_TO_TV.get(exch)
        if tv_prefix:
            return f"{tv_prefix}:{ticker}"
        logger.warning(f"OpenFIGI: unbekannter exchCode '{exch}' für '{ticker}'")
        return ticker  # Nur Ticker als Fallback
