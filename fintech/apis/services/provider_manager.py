import logging
from decimal import Decimal

from .comdirect import ComdirectRequest
from .alleaktien import AlleaktienRequest
from .justetf import JustEtfRequest
from .request_lib import KeyNotFoundWarning, KeyNotFoundError
from .soup_cache import SoupCache
from .exchange_rate_proxy import CurrencyProxy
from ...models_helper.asset_class import AssetClass

logger = logging.getLogger(__name__)

MAX_WKN_RETRIES = 2
MAX_PRICE_RETRIES = 2


class ProviderManager:

    def __init__(self):
        self.soup_cache = SoupCache()
        self.ex_proxy = CurrencyProxy()

        # Comdirect-Requester dynamisch aus AssetClass-Konfiguration aufbauen
        self.com_requester = {
            value: ComdirectRequest(
                base_url = url_template,
                cache    = self.soup_cache,
                id       = req_id,
            )
            for value, (url_template, req_id) in AssetClass.get_comdirect_config().items()
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

    def isin2wkn(self, isin: str, type_: str) -> str:
        """Return WKN for *isin* or None if all providers fail."""
        self._validate_type(type_)
        for attempt in range(MAX_WKN_RETRIES):
            try:
                if attempt == 0:
                    return self.com_requester[type_].isin2wkn(isin)
                if AssetClass.is_etf(type_):  # FIX: is_etf() statt Index-Magic
                    logger.info(f"Trying JustETF as WKN fallback for {isin}/{type_}")
                    return self.just_etf_request.isin2wkn(isin)
                return self.alle_aktien_request.isin2wkn(isin)
            except KeyNotFoundWarning:
                logger.warning(f"WKN not found for {isin}/{type_} attempt {attempt}")
            except KeyNotFoundError:
                logger.error(f"WKN definitively not found for {isin}/{type_}")
                return None

        logger.warning(f"WKN exhausted all providers for {isin}/{type_}")
        return None

    def isin2price(self, isin: str, type_: str) -> Decimal:
        """Return current price in EUR or None on failure.

        Provider chain:
          1. Comdirect  (alle Typen)
          2. AlleAktien (Fallback für Stock/ETF)
        """
        self._validate_type(type_)
        for attempt in range(MAX_PRICE_RETRIES):
            try:
                if attempt == 0:
                    price, currency = self.com_requester[type_].isin2price(isin)
                else:
                    if AssetClass.is_stock(type_):  # FIX: is_stock() statt Index-Magic
                        logger.info(f"Trying AlleAktien as price fallback for {isin}/{type_}")
                        _, price, currency, _ = self.alle_aktien_request.get_infos(isin)
                return self._convert_to_euro(price, currency)
            except KeyNotFoundWarning:
                logger.warning(f"Price not found for {isin}/{type_} attempt {attempt}")
            except KeyNotFoundError:
                logger.error(f"Price definitively not found for {isin}/{type_}")
                return None

        logger.warning(f"Price exhausted all providers for {isin}/{type_}")
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_type(self, type_: str) -> None:
        if not AssetClass.is_valid(type_):  # FIX: Flexibler mit is_valid()
            raise ValueError(
                f"Unsupported security type '{type_}'. "
                f"Valid values: {list(AssetClass.values)}. "
                f"Valid labels: {list(AssetClass.labels)}."
            )

    def _convert_to_euro(self, price: str, currency: str) -> Decimal:
        from ...libs.general.converter import string2dec
        dec_price = string2dec(price)
        if currency == "EUR":
            return dec_price
        rate = self.ex_proxy.get_rate(currency)
        return dec_price / rate
