import re
import logging
from decimal import Decimal, InvalidOperation
from typing import List, TypedDict

from .request_lib import StockRequest, KeyNotFoundWarning

logger = logging.getLogger(__name__)

WKN_HTML_PATTERN = (
    r'<span class="grey">WKN</span> '
    r'<span class="val pointer" data-copy-click="etf-second-id" data-copy-message=".*?"> '
    r'<span class="d-inline-block" id="etf-second-id">(.*?)</span> <span>'
)


class TopHolding(TypedDict):
    isin: str
    name: str
    percentage: Decimal


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

    def get_top_holdings(self, isin: str) -> List[TopHolding]:
        """
        Liefert die (kostenlos einsehbaren) Top-10-Holdings eines ETF von
        JustETF — mehr zeigt die Gratis-Ansicht nicht her. Ein leeres Ergebnis
        bedeutet entweder "kein ETF-Profil mit Holdings-Tabelle gefunden"
        (z.B. ungültige ISIN, aktiv gemanagter Fonds statt ETF) oder "ETF hat
        keine Aktien-Holdings" (z.B. Rohstoff-ETC).
        """
        logger.info(f"Request top holdings {isin} from JustETF")
        soup = self.fetch_soup(isin)

        table = soup.find("table", attrs={"data-testid": "etf-holdings_top-holdings_table"})
        if table is None:
            logger.info(f"Keine Holdings-Tabelle bei JustETF für {isin} gefunden")
            return []

        holdings: List[TopHolding] = []
        for row in table.find_all("tr", attrs={"data-testid": "etf-holdings_top-holdings_row"}):
            link = row.find("a", attrs={"data-testid": "tl_etf-holdings_top-holdings_link_name"})
            pct_span = row.find("span", attrs={"data-testid": "tl_etf-holdings_top-holdings_value_percentage"})
            if link is None or pct_span is None:
                continue

            href = link.get("href", "")
            holding_isin = href.rstrip("/").rsplit("/", 1)[-1].upper()
            name = link.get("title") or link.get_text(strip=True)

            try:
                percentage = Decimal(pct_span.get_text(strip=True).replace("%", "").replace(",", "."))
            except InvalidOperation:
                continue

            holdings.append({"isin": holding_isin, "name": name, "percentage": percentage})

        logger.info(f"JustETF Top-Holdings für {isin}: {len(holdings)} gefunden")
        return holdings
