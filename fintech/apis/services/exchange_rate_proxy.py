import requests
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from ...models import Asset
from ...models_helper.currency_class import CurrencyClass
from ...libs.general.converter import string2dec

logger = logging.getLogger(__name__)

RATE_TTL_MINUTES = 60   # Kurse nach 60 Minuten neu laden

class CurrencyProxy:

    def __init__(
        self,
        api_url: str = "https://api.frankfurter.dev/v1/latest",
        ttl_minutes: int = RATE_TTL_MINUTES,
    ):
        self.api_url = api_url
        self.ttl = timedelta(minutes=ttl_minutes)
        self.valid_currencies = set(CurrencyClass.values)
        self._data: dict | None = None
        self._fetched_at: datetime | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_rate(self, currency: str) -> Decimal:
        """Return the EUR-based exchange rate for *currency*.

        EUR itself is invalid (no conversion needed).
        Raises ValueError for unknown/unsupported currencies.
        Raises Exception when the API is unreachable.
        """
        if currency == "EUR":
            raise ValueError("EUR needs no conversion — handle before calling get_rate().")
        if currency not in self.valid_currencies:
            raise ValueError(f"Unsupported currency: '{currency}'.")

        self._ensure_fresh()

        if currency == "GBp":
            # GBp = pence; API returns GBP (pounds) → multiply by 100
            rate = string2dec(self._data["rates"]["GBP"]) * Decimal("100")
        else:
            rate = string2dec(self._data["rates"][currency])

        logger.info(f"Exchange rate {currency}/EUR = {rate}")
        return rate

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_stale(self) -> bool:
        """True when data has never been fetched or TTL has expired."""
        if self._data is None or self._fetched_at is None:
            return True
        return datetime.now(timezone.utc) - self._fetched_at > self.ttl  # war: nie erneuert

    def _ensure_fresh(self) -> None:
        if self._is_stale():
            self._fetch_rates()

    def _fetch_rates(self) -> None:
        logger.info(f"Fetching exchange rates from {self.api_url}")
        response = requests.get(self.api_url, timeout=10)
        response.raise_for_status()

        self._data = response.json()
        self._fetched_at = datetime.now(timezone.utc)
        logger.info(f"Exchange rates refreshed at {self._fetched_at.isoformat()}")
