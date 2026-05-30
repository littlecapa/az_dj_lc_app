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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _isin2symbol(self, isin: str) -> str:
        if isin in self._symbol_cache:
            return self._symbol_cache[isin]

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
            raise KeyNotFoundWarning(f"Yahoo Finance: no symbol found for {isin}")

        symbol = quotes[0]["symbol"]
        self._symbol_cache[isin] = symbol
        logger.info(f"Yahoo Finance: {isin} → {symbol}")
        return symbol

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
