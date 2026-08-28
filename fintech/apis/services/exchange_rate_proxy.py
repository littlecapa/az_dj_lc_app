import requests
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional

from django.conf import settings

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
        self._data: Optional[dict] = None
        self._fetched_at: Optional[datetime] = None
        # Alpha Vantage: schmaler Fallback für Währungen, die frankfurter.dev
        # nicht führt (z.B. TWD) — eigenes Cache-Dict, gleiches TTL.
        self._av_cache: dict[str, tuple[Decimal, datetime]] = {}

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
        elif currency == "ZAc":
            # ZAc = Rand-Cents; API returns ZAR (Rand) → multiply by 100
            rate = string2dec(self._data["rates"]["ZAR"]) * Decimal("100")
        elif currency in self._data["rates"]:
            rate = string2dec(self._data["rates"][currency])
        else:
            # frankfurter.dev (ECB-Referenzkurse) führt diese Währung nicht (z.B.
            # TWD) — Alpha Vantage als schmaler Fallback, siehe FIN-442.
            rate = self._get_alphavantage_rate(currency)

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

    def _get_alphavantage_rate(self, currency: str) -> Decimal:
        """EUR-Rate für eine Währung, die frankfurter.dev nicht führt, über Alpha
        Vantage — bewusst nur als schmaler Einzel-Fallback (Free-Tier: 25 Requests/
        Tag), nicht als vollwertiger Kurs-Provider. Ergebnis wird pro Instanz
        gecacht (gleiches TTL wie die frankfurter.dev-Kurse)."""
        cached = self._av_cache.get(currency)
        if cached and datetime.now(timezone.utc) - cached[1] <= self.ttl:
            return cached[0]

        api_key = getattr(settings, "ALPHAVANTAGE_API_KEY", None)
        if not api_key:
            raise ValueError(
                f"Unsupported currency: '{currency}' (nicht in frankfurter.dev, "
                f"und ALPHAVANTAGE_API_KEY nicht konfiguriert)."
            )

        logger.info(f"Fetching {currency}/EUR rate from Alpha Vantage (frankfurter.dev fallback)")
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": currency,
                "to_currency": "EUR",
                "apikey": api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        try:
            # Alpha Vantage liefert "1 <currency> = X EUR" — invertieren, damit das
            # Ergebnis wie bei frankfurter.dev "1 EUR = X <currency>" bedeutet
            # (_convert_to_euro rechnet price_in_currency / rate = price_in_EUR).
            av_rate = string2dec(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        except KeyError:
            raise ValueError(f"Alpha Vantage lieferte keinen Kurs für {currency}/EUR: {data}")

        rate = Decimal("1") / av_rate
        self._av_cache[currency] = (rate, datetime.now(timezone.utc))
        return rate
