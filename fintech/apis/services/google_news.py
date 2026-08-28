"""
Google News RSS — inoffiziell (kein API-Key nötig, aber auch keine offizielle
API). Der Feed selbst schreibt im <copyright>-Tag fest, dass er nur für
"rendering Google News results within a personal feed reader for personal,
non-commercial use" gedacht ist — passend für diese private Portfolio-
News-Seite. Ergänzt Yahoo Finance um deutschsprachige Abdeckung, die dort
oft dünn ist (z.B. deutsche Nebenwerte).
"""
import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

RSS_URL = "https://news.google.com/rss/search"
HEADERS = {"User-Agent": "Mozilla/5.0"}


class GoogleNewsRequest:

    def __init__(self):
        self.id = "google_news"

    def search_news(self, query: str, count: int = 5, lang: str = "de", country: str = "DE") -> list[dict]:
        """Return up to *count* news items matching *query*.

        Jedes Item: {'title', 'link', 'source', 'published_at', 'thumbnail_url'}
        (thumbnail_url ist bei Google News RSS immer None — der Feed liefert
        keine Bilder, anders als Yahoo Finance)."""
        logger.info(f"Request Google News RSS for '{query}'")
        resp = requests.get(
            RSS_URL,
            params={"q": query, "hl": lang, "gl": country, "ceid": f"{country}:{lang}"},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall("./channel/item")[:count]

        results = []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            if not title or not link:
                continue

            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else ""
            # Titel enthält oft redundant " - <Quelle>" am Ende — abschneiden falls vorhanden.
            if source and title.endswith(f" - {source}"):
                title = title[: -(len(source) + 3)].strip()

            published_at = None
            pub_date_raw = item.findtext("pubDate")
            if pub_date_raw:
                try:
                    published_at = parsedate_to_datetime(pub_date_raw)
                except (TypeError, ValueError):
                    logger.warning(f"Google News: pubDate nicht parsbar: '{pub_date_raw}'")

            results.append({
                "title": title,
                "link": link,
                "source": source,
                "published_at": published_at,
                "thumbnail_url": None,
            })
        return results
