"""
Django Management Command: update_news

Holt aktuelle News (Yahoo Finance + Google News RSS) für alle Aktien mit
Look-Through-Gesamtwert über --min-value (Basis: dieselbe Berechnung wie
/fintech/overall-stocks/, siehe services.get_news_target_rows). Neue Artikel
werden in NewsArticle gespeichert (dedupliziert über den Link).

Bewusst als periodischer Cron-Lauf gedacht, nicht als Live-Abruf beim
Seitenaufruf von /fintech/news-feed/ — sonst würde jeder Page-Load Dutzende
externe Requests an Yahoo/Google auslösen.

Aufruf:
python manage.py update_news
python manage.py update_news --min-value 5000
python manage.py update_news --dry-run
"""

import logging
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from fintech.models import Asset, NewsArticle
from fintech.services import get_news_target_rows
from fintech.apis.services.yahoo_finance import YahooFinanceRequest
from fintech.apis.services.google_news import GoogleNewsRequest

logger = logging.getLogger(__name__)

DEFAULT_MIN_VALUE = Decimal("3000")
NEWS_PER_COMPANY_PER_PROVIDER = 5


class Command(BaseCommand):
    help = "Holt News (Yahoo Finance + Google News) für Aktien mit Look-Through-Wert über einer Schwelle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-value", type=str, default=str(DEFAULT_MIN_VALUE),
            help="Nur Aktien mit Look-Through-Gesamtwert über diesem EUR-Betrag (Default: 3000).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Nichts speichern, nur anzeigen.")

    def handle(self, *args, **options):
        try:
            min_value = Decimal(options["min_value"])
        except InvalidOperation:
            raise CommandError(f"--min-value '{options['min_value']}' ist keine gültige Zahl.")
        dry_run = options["dry_run"]

        rows = get_news_target_rows(min_value)
        self.stdout.write(f"{len(rows)} Aktie(n) über {min_value} € Look-Through-Wert.")
        if not rows:
            return

        yahoo = YahooFinanceRequest()
        google = GoogleNewsRequest()

        created = 0
        skipped_duplicate = 0
        errors = 0

        for row in rows:
            name = row["name"]
            isin = row["isin"]
            # compute_stock_lookthrough_rows() liefert nur die ISIN, nicht das
            # Asset-Objekt (row_key kann bei manuell erfassten Fonds-Positionen
            # ohne Match auch ein synthetischer Key statt einer ISIN sein).
            asset = Asset.objects.filter(isin=isin).first() if isin else None

            if isin:
                try:
                    items = yahoo.isin2news(isin, count=NEWS_PER_COMPANY_PER_PROVIDER)
                    for item in items:
                        result = self._save(item, asset, name, NewsArticle.Provider.YAHOO, dry_run)
                        created += result == "created"
                        skipped_duplicate += result == "duplicate"
                except Exception as exc:
                    errors += 1
                    logger.warning(f"Yahoo News fehlgeschlagen für {isin} ({name}): {exc}")

            try:
                items = google.search_news(f"{name} Aktie", count=NEWS_PER_COMPANY_PER_PROVIDER)
                for item in items:
                    result = self._save(item, asset, name, NewsArticle.Provider.GOOGLE, dry_run)
                    created += result == "created"
                    skipped_duplicate += result == "duplicate"
            except Exception as exc:
                errors += 1
                logger.warning(f"Google News fehlgeschlagen für {name}: {exc}")

        self.stdout.write(self.style.SUCCESS(
            f"Fertig: {created} neue Artikel, {skipped_duplicate} bereits bekannt, {errors} Fehler."
        ))

    def _save(self, item: dict, asset, company_name: str, provider: str, dry_run: bool) -> str:
        if dry_run:
            self.stdout.write(f"DRY [{provider}] {item['title']} — {item['link'][:70]}")
            return "dry"

        _, was_created = NewsArticle.objects.get_or_create(
            link=item["link"],
            defaults={
                "asset": asset,
                "company_name": company_name,
                "title": item["title"][:500],
                "source": item["source"][:100],
                "provider": provider,
                "thumbnail_url": item.get("thumbnail_url"),
                "published_at": item.get("published_at"),
            },
        )
        return "created" if was_created else "duplicate"
