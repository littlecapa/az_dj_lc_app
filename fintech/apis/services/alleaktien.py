import re
import logging

from .request_lib import StockRequest, KeyNotFoundWarning

logger = logging.getLogger(__name__)


class AlleaktienRequest(StockRequest):

    def isin2wkn(self, isin: str) -> str:
        logger.info(f"Request isin2wkn {isin} from AlleAktien")
        soup = self.fetch_soup(isin)
        wkn, _, _, _ = self.extract_from_soup(soup)
        return wkn

    def get_infos(self, isin: str) -> tuple:
        """Return (wkn, current_price, currency, symbol) for *isin*."""
        soup = self.fetch_soup(isin)
        return self.extract_from_soup(soup)

    def extract_from_soup(self, soup) -> tuple:
        price_pattern = r"(?P<price>\d{1,3},\d{2})"
        currency_pattern = r"(?P<currency>[A-Za-z]{3}|\$|€)"
        full_pattern = (
            r'class="whitespace-nowrap live-quote flex flex-row price text-black">'
            rf"<div>({price_pattern})\s*({currency_pattern})"
        )

        match = re.search(full_pattern, str(soup))
        if match:
            price = match.group(2)
            currency = match.group(3)

            title_match = re.search(r'<meta content="(.*?)" name="twitter:title"/>', str(soup))
            if title_match:
                parts = [p.strip() for p in title_match.group(1).split("|")]
                if len(parts) >= 4:
                    symbol = parts[1].strip()
                    wkn = parts[3].strip()
                    return wkn, price, currency, symbol

        raise KeyNotFoundWarning(f"ISIN not found on AlleAktien")
