from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)


class SoupCache:
    def __init__(self, max_age_minutes: int = 10):
        self.cache: dict = {}
        self.max_age = timedelta(minutes=max_age_minutes)

    def put(self, isin: str, soup, requester_id: str, base_url: str) -> None:
        """Store soup with a UTC timestamp."""
        key = self._key(isin, requester_id, base_url)
        self.cache[key] = {
            "soup": soup,
            "timestamp": datetime.now(timezone.utc),   # war: datetime.now() — kein Timezone
        }
        logger.info(f"Cache put  [{requester_id}] {isin}")

    def get(self, isin: str, requester_id: str, base_url: str):
        """Return cached soup if it exists and is not expired, else None."""
        key = self._key(isin, requester_id, base_url)
        entry = self.cache.get(key)

        if entry is None:
            logger.info(f"Cache miss [{requester_id}] {isin}")
            return None

        age = datetime.now(timezone.utc) - entry["timestamp"]
        if age > self.max_age:
            del self.cache[key]
            logger.info(f"Cache expired [{requester_id}] {isin} (age {age})")
            return None

        logger.info(f"Cache hit  [{requester_id}] {isin}")
        return entry["soup"]

    @staticmethod
    def _key(isin: str, requester_id: str, base_url: str) -> tuple:
        return (isin, requester_id, base_url)
