import logging
import requests

from .request_lib import KeyNotFoundWarning, KeyNotFoundError

logger = logging.getLogger(__name__)

SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
CHART_URL  = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS    = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


class YahooFinanceRequest:
    """Two-step Yahoo Finance lookup: ISIN → ticker symbol → current price."""

    def __init__(self):
        self.id = "yahoo_finance"
        self._symbol_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def isin2price(self, isin: str) -> tuple[str, str]:
        """Return (price_str, currency) for *isin*. Price uses dot as decimal separator."""
        logger.info(f"Request isin2price {isin} from Yahoo Finance")
        symbol = self._isin2symbol(isin)
        return self._symbol2price(symbol, isin)

    def isin2name(self, isin: str) -> str:
        """Return the long name for *isin* from Yahoo Finance search."""
        logger.info(f"Request isin2name {isin} from Yahoo Finance")
        return self._fetch_name(isin)

    def isin2week52(self, isin: str) -> dict:
        """Return {'high': str, 'low': str, 'currency': str, 'symbol': str} for *isin*."""
        logger.info(f"Request isin2week52 {isin} from Yahoo Finance")
        symbol = self._isin2symbol(isin)
        result = self._symbol2week52(symbol, isin)
        result['symbol'] = symbol  # Symbol mitgeben, damit Caller es in DB speichern kann
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search(self, isin: str) -> dict:
        """Raw Yahoo Finance search result (first quote) for *isin*."""
        resp = requests.get(
            SEARCH_URL,
            params={"q": isin, "quotesCount": 1, "newsCount": 0},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code in (400, 404):
            raise KeyNotFoundWarning(f"Yahoo Finance search returned {resp.status_code} for {isin}")
        resp.raise_for_status()

        quotes = resp.json().get("quotes", [])
        if not quotes:
            raise KeyNotFoundWarning(f"Yahoo Finance: no result found for {isin}")
        return quotes[0]

    def _isin2symbol(self, isin: str) -> str:
        if isin in self._symbol_cache:
            return self._symbol_cache[isin]

        # DB-Lookup zuerst: Asset.symbol verwenden wenn vorhanden (spart Yahoo-API-Call)
        try:
            from fintech.models import Asset as _Asset
            asset = _Asset.objects.filter(isin=isin).only('symbol').first()
            if asset and asset.symbol:
                symbol = asset.symbol
                self._symbol_cache[isin] = symbol
                logger.info(f"Yahoo Finance: {isin} → {symbol} (aus DB)")
                return symbol
        except Exception:
            pass  # kein Django-Kontext (z.B. Tests) → ignorieren

        # Yahoo Search als Fallback
        quote  = self._search(isin)
        symbol = quote["symbol"]
        self._symbol_cache[isin] = symbol
        logger.info(f"Yahoo Finance: {isin} → {symbol} (Yahoo Search)")

        # Symbol in DB persistieren, damit nächster Aufruf DB-Lookup nutzt
        try:
            from fintech.models import Asset as _Asset
            _Asset.objects.filter(isin=isin, symbol__isnull=True).update(symbol=symbol)
            _Asset.objects.filter(isin=isin, symbol='').update(symbol=symbol)
        except Exception:
            pass  # Silent – DB-Update ist best-effort

        return symbol

    def _fetch_name(self, isin: str) -> str:
        quote = self._search(isin)
        name  = quote.get("longname") or quote.get("shortname") or ""
        name  = name.strip()
        if not name:
            raise KeyNotFoundWarning(f"Yahoo Finance: no name found for {isin}")
        logger.info(f"Yahoo Finance name [{isin}]: {name}")
        return name

    def _symbol2price(self, symbol: str, isin: str) -> tuple[str, str]:
        url  = CHART_URL.format(symbol=symbol)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code in (400, 404):
            raise KeyNotFoundWarning(f"Yahoo Finance chart returned {resp.status_code} for {symbol}")
        resp.raise_for_status()

        try:
            meta     = resp.json()["chart"]["result"][0]["meta"]
            price    = meta["regularMarketPrice"]
            currency = meta["currency"]
        except (KeyError, IndexError, TypeError) as exc:
            raise KeyNotFoundWarning(f"Yahoo Finance: unexpected chart response for {symbol}: {exc}")

        # GBp (Pence) → GBP (Pfund) normalisieren
        if currency == "GBp":
            price    = price / 100
            currency = "GBP"

        logger.info(f"Yahoo Finance price [{isin}]: {price} {currency}")
        return str(price), currency

    def _symbol2week52(self, symbol: str, isin: str) -> dict:
        url  = CHART_URL.format(symbol=symbol)
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code in (400, 404):
            raise KeyNotFoundWarning(f"Yahoo Finance chart returned {resp.status_code} for {symbol}")
        resp.raise_for_status()

        try:
            meta = resp.json()["chart"]["result"][0]["meta"]
            high    = meta["fiftyTwoWeekHigh"]
            low     = meta["fiftyTwoWeekLow"]
            currency = meta["currency"]
            current = meta["regularMarketPrice"]
        except (KeyError, IndexError, TypeError) as exc:
            raise KeyNotFoundWarning(f"Yahoo Finance: no 52W data for {symbol}: {exc}")

        # GBp (Pence) → GBP (Pfund) normalisieren: Yahoo gibt UK-Kurse in Pence zurück.
        # 1 GBP = 100 GBp → alle Werte durch 100 teilen, Währung auf "GBP" setzen.
        if currency == "GBp":
            high    = high    / 100
            low     = low     / 100
            current = current / 100
            currency = "GBP"
            logger.info(f"Yahoo Finance 52W [{isin}]: GBp→GBP normalisiert")

        logger.info(f"Yahoo Finance 52W [{isin}]: symbol={symbol} cur={current} {currency} 52H={high} 52T={low}")

        # Plausibilitätsprüfung: 52W-Daten verwerfen wenn offensichtlich fehlerhaft.
        # Yahoo liefert manchmal kaputte Werte für dünn gehandelte Listings (.SG, .L etc.),
        # erkennbar an zwei Mustern:
        #   1. current > high * 1.2  → Kurs über dem angeblichen 52W-Hoch (unmöglich)
        #   2. high > current * 5    → 52W-Hoch >5x über aktuellem Kurs (Reverse-Split-Artefakt
        #                              oder falsche Zeitreihe — z.B. HSTE.L: 65.99 vs. 6.61)
        try:
            f_cur  = float(current)
            f_high = float(high)
            f_low  = float(low)
            # Check 1: Kurs über 52W-Hoch (physisch unmöglich, fehlerhafte .SG-Daten)
            if f_cur > f_high * 1.20:
                raise KeyNotFoundWarning(
                    f"Yahoo 52W invalid for {symbol}: current={f_cur} > high={f_high}*1.2"
                )
            # Check 2: 52W-Hoch >5x aktueller Kurs (Reverse-Split-Artefakt, z.B. HSTE.L)
            if f_high > f_cur * 5.0:
                raise KeyNotFoundWarning(
                    f"Yahoo 52W invalid for {symbol}: high={f_high} > current={f_cur}*5"
                )
            # Check 3: 52W-Spanne >8x (high/low-Ratio) → Daten aus spärlich gehandeltem
            # Sekundärlisting (z.B. Stuttgart .SG für NO/DK Aktien), 52W-Tief unrealistisch.
            # Equinor Stuttgart: high=38, low=3.15 → ratio=12.1 → INVALID
            # Equinor Oslo:      high=422, low=226 → ratio=1.9  → OK
            if f_low > 0 and f_high / f_low > 8.0:
                raise KeyNotFoundWarning(
                    f"Yahoo 52W invalid for {symbol}: high/low={f_high/f_low:.1f} > 8 "
                    f"(likely sparse secondary listing)"
                )
        except KeyNotFoundWarning:
            raise
        except (TypeError, ValueError):
            pass

        return {"high": str(high), "low": str(low), "currency": currency, "current": str(current)}
