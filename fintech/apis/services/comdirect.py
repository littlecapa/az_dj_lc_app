import re
import logging

from django.http import Http404

from .request_lib import StockRequest, KeyNotFoundWarning, KeyNotFoundError
from ...models import Asset
from ...models_helper.currency_class import CurrencyClass

logger = logging.getLogger(__name__)

WKN_PATTERN = r"WKN:\s*(?P<WKN>[A-Z0-9]{6}),\s*"
NOT_FOUND_TEXT = "Die gewünschte Seite wurde nicht gefunden"
ERROR_CLASS = "error-page--headline headline headline--h1"


class ComdirectRequest(StockRequest):

    def isin2wkn(self, isin: str) -> str:
        logger.info(f"Request isin2wkn {isin} from Comdirect")
        soup = self.fetch_soup(isin)
        self._check_soup_ok(soup)
        return self._extract_wkn(soup, isin)

    def isin2price(self, isin: str) -> tuple[str, str]:
        logger.info(f"Request isin2price {isin} from Comdirect")
        soup = self.fetch_soup(isin)
        self._check_soup_ok(soup)
        return self._extract_price(soup, isin)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_soup_ok(self, soup) -> None:
        """Raise Http404 or KeyNotFoundError when the page is not usable."""
        if soup.find(lambda tag: tag.name is not None and NOT_FOUND_TEXT in tag.text):
            raise Http404(f"Comdirect returned 'page not found' page.")
        if self.not_found_in_soup(soup, tag="h1", pattern=ERROR_CLASS):
            raise KeyNotFoundError("Unknown Soup Format on Comdirect")

    def _extract_wkn(self, soup, isin: str) -> str:
        match = re.search(WKN_PATTERN, str(soup))
        if match:
            wkn = match.group("WKN")
            logger.info(f"WKN found on Comdirect: {wkn}")
            return wkn
        raise KeyNotFoundWarning(f"WKN not found on Comdirect for {isin}")

    def _extract_price(self, soup, isin: str) -> tuple[str, str]:
        currency_pattern = CurrencyClass.get_currency_pattern()
        price_pattern = (
            r"Kurs:\s*(?P<Kurs>\d{1,5},\d{1,4})\s*"
            rf"(?P<Waehrung>{currency_pattern}),?"
        )

        meta_tag = soup.find("meta", {"itemprop": "description"})
        if not meta_tag:
            raise KeyNotFoundWarning(f"No meta description tag found for {isin}")

        content = meta_tag.get("content", "")
        logger.info(f"Comdirect meta content: {content}")

        match = re.search(price_pattern, content)
        if match:
            price = match.group("Kurs")
            currency = match.group("Waehrung")
            logger.info(f"Price found: {price} {currency}")
            return price, currency

        raise KeyNotFoundWarning(f"Price not found in Comdirect meta for {isin}: '{content}'")
