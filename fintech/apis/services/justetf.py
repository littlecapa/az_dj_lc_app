import re
import logging

from .request_lib import StockRequest, KeyNotFoundWarning

logger = logging.getLogger(__name__)

WKN_HTML_PATTERN = (
    r'<span class="grey">WKN</span> '
    r'<span class="val pointer" data-copy-click="etf-second-id" data-copy-message=".*?"> '
    r'<span class="d-inline-block" id="etf-second-id">(.*?)</span> <span>'
)


class JustEtfRequest(StockRequest):

    def isin2wkn(self, isin: str) -> str:
        logger.info(f"Request isin2wkn {isin} from JustETF")
        soup = self.fetch_soup(isin)
        return self.extract_wkn_from_soup(soup)

    def extract_wkn_from_soup(self, soup) -> str:
        match = re.search(WKN_HTML_PATTERN, str(soup))
        if match:
            wkn = match.group(1)
            logger.info(f"WKN found in JustEtf: {wkn}")
            return wkn

        raise KeyNotFoundWarning("ISIN not found on JustETF")
