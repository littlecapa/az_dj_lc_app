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
        """ISIN → Yahoo-Ticker-Symbol (z.B. '9880.HK', 'RHM.DE').
        Hinweis: Das ist das Yahoo-Format, NICHT das TradingView-Format (HKEX:9880).
        Asset.symbol speichert TradingView-Symbole — diese dürfen hier nicht verwendet werden."""
        if isin in self._symbol_cache:
            return self._symbol_cache[isin]

        quote  = self._search(isin)
        symbol = quote["symbol"]
        self._symbol_cache[isin] = symbol
        logger.info(f"Yahoo Finance: {isin} → {symbol}")
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

        return {"high": str(high), "low": str(low), "currency": currency, "current": str(current)}
