import logging
from decimal import Decimal

from .comdirect import ComdirectRequest
from .alleaktien import AlleaktienRequest
from .justetf import JustEtfRequest
from .request_lib import KeyNotFoundWarning, KeyNotFoundError
from .soup_cache import SoupCache
from .exchange_rate_proxy import CurrencyProxy

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = ("Stock", "ETF", "Certificate")
MAX_WKN_RETRIES = 2
MAX_PRICE_RETRIES = 2


class ProviderManager:

    def __init__(self):
        self.soup_cache = SoupCache()
        self.ex_proxy = CurrencyProxy()

        self.com_requester = {
            "Stock":       ComdirectRequest("https://www.comdirect.de/inf/aktien/{isin}",     cache=self.soup_cache, id="com_stock"),
            "ETF":         ComdirectRequest("https://www.comdirect.de/inf/etfs/{isin}",        cache=self.soup_cache, id="com_etf"),
            "Certificate": ComdirectRequest("https://www.comdirect.de/inf/zertifikate/{isin}", cache=self.soup_cache, id="com_cert"),
        }
        self.alle_aktien_request = AlleaktienRequest(
            "https://www.alleaktien.com/data/{isin}", cache=self.soup_cache, id="alle"
        )
        self.just_etf_request = JustEtfRequest(
            "https://www.justetf.com/de/etf-profile.html?isin={isin}", cache=self.soup_cache, id="just_etf"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def isin2wkn(self, isin: str, type: str) -> str:
        """Return WKN for *isin* or None if all providers fail."""
        self._validate_type(type)
        for attempt in range(MAX_WKN_RETRIES):
            try:
                if attempt == 0:
                    return self.com_requester[type].isin2wkn(isin)
                # Fallback provider
                if type == "ETF":
                    return self.just_etf_request.isin2wkn(isin)
                return self.alle_aktien_request.isin2wkn(isin)
            except KeyNotFoundWarning:
                logger.warning(f"WKN not found for {isin}/{type} attempt {attempt}")
            except KeyNotFoundError:
                logger.error(f"WKN definitively not found for {isin}/{type}")
                return None

        logger.warning(f"WKN exhausted all providers for {isin}/{type}")
        return None

    def isin2price(self, isin: str, type: str) -> Decimal:
        """Return current price in EUR or None on failure."""
        self._validate_type(type)
        for attempt in range(MAX_PRICE_RETRIES):
            try:
                price, currency = self.com_requester[type].isin2price(isin)
                return self._convert_to_euro(price, currency)
            except KeyNotFoundWarning:
                logger.warning(f"Price not found for {isin}/{type} attempt {attempt}")
            except KeyNotFoundError:
                logger.error(f"Price definitively not found for {isin}/{type}")
                return None

        logger.warning(f"Price exhausted all providers for {isin}/{type}")
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_type(self, type: str):
        if type not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported security type '{type}'. Choose from {SUPPORTED_TYPES}.")

    def _convert_to_euro(self, price: str, currency: str) -> Decimal:
        from ...libs.general.converter import string2dec
        dec_price = string2dec(price)
        if currency == "EUR":
            return dec_price
        rate = self.ex_proxy.get_rate(currency)
        return dec_price / rate
