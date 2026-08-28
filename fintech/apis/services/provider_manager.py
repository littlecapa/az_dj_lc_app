import logging
from decimal import Decimal
from typing import Optional

from .comdirect import ComdirectRequest
from .alleaktien import AlleaktienRequest
from .justetf import JustEtfRequest
from .yahoo_finance import YahooFinanceRequest
from .request_lib import KeyNotFoundWarning, KeyNotFoundError
from .soup_cache import SoupCache
from .exchange_rate_proxy import CurrencyProxy
from ...models_helper.asset_class import AssetClass
import requests

logger = logging.getLogger(__name__)

MAX_WKN_RETRIES = 2

# If two primary providers differ by more than this fraction, a third provider
# is consulted and the median of all available results is returned.
PRICE_DELTA_THRESHOLD = Decimal("0.01")  # 1 %


class ProviderManager:

    def __init__(self):
        self.soup_cache = SoupCache()
        self.ex_proxy   = CurrencyProxy()

        self.com_requester = {
            value: ComdirectRequest(
                base_url=url_template,
                cache=self.soup_cache,
                id=req_id,
            )
            for value, (url_template, req_id) in AssetClass.get_comdirect_config().items()
        }

        self.alle_aktien_request = AlleaktienRequest(
            "https://www.alleaktien.com/data/{isin}", cache=self.soup_cache, id="alle"
        )
        self.just_etf_request = JustEtfRequest(
            "https://www.justetf.com/de/etf-profile.html?isin={isin}", cache=self.soup_cache, id="just_etf"
        )
        self.yahoo_request = YahooFinanceRequest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def isin2wkn(self, isin: str, type_: str) -> Optional[str]:
        """Return WKN for *isin* or None if all providers fail."""
        self._validate_type(type_)
        for attempt in range(MAX_WKN_RETRIES):
            try:
                if attempt == 0:
                    return self.com_requester[type_].isin2wkn(isin)
                if AssetClass.is_etf(type_):
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

    def isin2price(self, isin: str, type_: str, yahoo_symbol: Optional[str] = None) -> Optional[Decimal]:
        """Return current price in EUR or None on failure.

        Provider strategy:
          1. Comdirect + Yahoo Finance (primary pair, queried in sequence)
          2. If their prices differ by more than PRICE_DELTA_THRESHOLD,
             AlleAktien is consulted as a tiebreaker.
          3. The median of all available EUR prices is returned.

        This catches the sporadic bad prices that have been observed recently.

        yahoo_symbol: manuelles Yahoo-Ticker-Override (Asset.yahoo_symbol),
        falls Yahoos eigene ISIN-Suche für dieses Asset nichts findet.
        """
        self._validate_type(type_)

        prices: list[Decimal] = []

        # --- Primary provider: Comdirect ---
        comdirect_price = self._fetch_comdirect_price(isin, type_)
        if comdirect_price is not None:
            prices.append(comdirect_price)

        # --- Secondary provider: Yahoo Finance ---
        yahoo_price = self._fetch_yahoo_price(isin, symbol_override=yahoo_symbol)
        if yahoo_price is not None:
            prices.append(yahoo_price)

        if not prices:
            logger.error(f"isin2price: all primary providers failed for {isin}/{type_}")
            return None

        if len(prices) == 1:
            logger.warning(f"isin2price: only one provider succeeded for {isin}/{type_}")
            return prices[0]

        # --- Delta check ---
        delta_pct = self._delta_pct(prices[0], prices[1])
        logger.info(
            f"isin2price [{isin}]: Comdirect={prices[0]:.4f}, Yahoo={prices[1]:.4f}, "
            f"delta={delta_pct:.2%}"
        )

        if delta_pct > PRICE_DELTA_THRESHOLD:
            logger.warning(
                f"isin2price [{isin}]: price delta {delta_pct:.2%} exceeds threshold "
                f"{PRICE_DELTA_THRESHOLD:.0%} — consulting tiebreaker"
            )
            tiebreaker = self._fetch_tiebreaker_price(isin, type_)
            if tiebreaker is not None:
                prices.append(tiebreaker)
                logger.info(f"isin2price [{isin}]: tiebreaker={tiebreaker:.4f}")

        result = self._median(prices)
        logger.info(f"isin2price [{isin}]: final={result:.4f} (from {len(prices)} providers)")
        return result

    # ------------------------------------------------------------------
    # Provider fetch helpers — each returns Decimal | None
    # ------------------------------------------------------------------

    def _fetch_comdirect_price(self, isin: str, type_: str) -> Optional[Decimal]:
        try:
            price, currency = self.com_requester[type_].isin2price(isin)
            return self._convert_to_euro(price, currency)
        except (KeyNotFoundWarning, KeyNotFoundError) as exc:
            # STOCK kann als FOND bei Comdirect gelistet sein (z.B. UK Investment Trusts)
            if type_ == AssetClass.STOCK.value:
                logger.info(f"Comdirect STOCK fehlgeschlagen für {isin} — versuche FOND-URL als Fallback")
                try:
                    price, currency = self.com_requester[AssetClass.FOND.value].isin2price(isin)
                    logger.info(f"FOND-Fallback erfolgreich für {isin}")
                    return self._convert_to_euro(price, currency)
                except (KeyNotFoundWarning, KeyNotFoundError):
                    pass
            logger.warning(f"Comdirect price failed for {isin}: {exc}")
            return None

    def _fetch_yahoo_price(self, isin: str, symbol_override: Optional[str] = None) -> Optional[Decimal]:
        try:
            price, currency = self.yahoo_request.isin2price(isin, symbol_override=symbol_override)
            return self._convert_to_euro(price, currency)
        except (KeyNotFoundWarning, KeyNotFoundError) as exc:
            logger.warning(f"Yahoo Finance price failed for {isin}: {exc}")
            return None
        except Exception as exc:
            logger.error(f"Yahoo Finance unexpected error for {isin}: {exc}")
            return None

    def _fetch_tiebreaker_price(self, isin: str, type_: str) -> Optional[Decimal]:
        """AlleAktien is used as tiebreaker (Stocks only; no-op for ETFs/Indices)."""
        if not AssetClass.is_stock(type_):
            logger.info(f"Tiebreaker: AlleAktien skipped for type {type_} ({isin})")
            return None
        try:
            _, price, currency, _ = self.alle_aktien_request.get_infos(isin)
            return self._convert_to_euro(price, currency)
        except (KeyNotFoundWarning, KeyNotFoundError) as exc:
            logger.warning(f"AlleAktien tiebreaker failed for {isin}: {exc}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_type(self, type_: str) -> None:
        if not AssetClass.is_valid(type_):
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

    @staticmethod
    def _delta_pct(a: Decimal, b: Decimal) -> Decimal:
        """Relative difference between two prices (always positive)."""
        if a == 0 and b == 0:
            return Decimal(0)
        return abs(a - b) / max(abs(a), abs(b))

    @staticmethod
    def _median(values: list[Decimal]) -> Decimal:
        if not values:
            raise ValueError("Cannot compute median of empty list")
        s = sorted(values)
        n = len(s)
        mid = n // 2
        if n % 2 == 1:
            return s[mid]
        return (s[mid - 1] + s[mid]) / 2
