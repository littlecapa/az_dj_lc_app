import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class KeyNotFoundWarning(Exception):
    """Raised when a key is not found but a fallback provider may succeed."""

    def __init__(self, key, message="Key not found"):
        self.key = key
        self.message = f"{message}: {key}"
        super().__init__(self.message)


class KeyNotFoundError(Exception):
    """Raised when a key is definitively not found (no fallback useful)."""

    def __init__(self, key, message="Key not found"):
        self.key = key
        self.message = f"{message}: {key}"
        super().__init__(self.message)


class StockRequest:
    def __init__(self, base_url: str, cache, id: str):
        self.base_url = base_url
        self.cache = cache
        self.id = id

    def fetch_soup(self, isin: str) -> BeautifulSoup:
        """Fetch (or return cached) BeautifulSoup for *isin*."""
        cached = self.cache.get(isin=isin, requester_id=self.id, base_url=self.base_url)
        if cached:
            return cached

        url = self.base_url.replace("{isin}", isin)
        logger.info(f"Fetching {url}")
        response = requests.get(url, timeout=10)
        response.encoding = "utf-8"

        if response.status_code == 404 or response.status_code == 400:
            raise KeyNotFoundWarning(f"Provider returned {response.status_code} for ISIN {isin}")
        response.raise_for_status()  # 5xx und sonstige Fehler → echte Exception

        soup = BeautifulSoup(response.content, "html.parser")
        self.cache.put(isin=isin, soup=soup, requester_id=self.id, base_url=self.base_url)
        return soup

    def not_found_in_soup(self, soup: BeautifulSoup, tag: str, pattern: str):
        return soup.find(tag, class_=pattern)
