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

        logger.info(f"Yahoo Finance price [{isin}]: {price} {currency}")
        return str(price), currency
