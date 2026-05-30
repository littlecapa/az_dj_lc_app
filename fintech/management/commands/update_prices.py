"""
Django Management Command: update_prices

Aktualisiert den Kurs aller Assets deren Preis fehlt oder älter als 1h ist.

Aufruf:
python manage.py update_prices
python manage.py update_prices --dry-run
python manage.py update_prices --isin DE0007164600
python manage.py update_prices --asset-class STOCK
python manage.py update_prices --asset-class ETF --asset-class ETC
"""

import asyncio
import logging
from datetime import timedelta
from typing import Optional
from decimal import Decimal

from asgiref.sync import async_to_sync, sync_to_async
from django.core.management.base import BaseCommand
from django.utils import timezone

from fintech.models import Asset, Price
from fintech.models_helper.asset_class import AssetClass
from fintech.apis.services.provider_manager import ProviderManager

logger = logging.getLogger(__name__)

PRICE_MAX_AGE = timedelta(hours=1)
CONCURRENCY = 10

# Maximale erlaubte Tagesveränderung pro Asset-Klasse (in %).
# Preise die stärker abweichen werden als Scraping-Fehler gewertet und verworfen.
MAX_CHANGE_PERC: dict[str, Decimal] = {
    AssetClass.ETF:        Decimal("10"),
    AssetClass.ETC:        Decimal("10"),
    AssetClass.FOND:       Decimal("10"),
    AssetClass.STOCK:      Decimal("8"),   # enger: blockt ~7% Tokio/Frankfurt-Gap für JP-Aktien
    AssetClass.DERIVATIVE: Decimal("40"),
    AssetClass.CRYPTO:     Decimal("30"),
}


class Command(BaseCommand):
    help = "Aktualisiert Kurse für alle Assets die fehlen oder älter als 1h sind."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen welche Assets aktualisiert würden, nichts speichern.",
        )
        parser.add_argument(
            "--isin",
            type=str,
            help="Nur ein bestimmtes Asset aktualisieren.",
        )
        parser.add_argument(
            "--asset-class",
            type=str,
            action="append",
            dest="asset_classes",
            choices=list(AssetClass.values),
            metavar="CLASS",
            help=(
                f"Nur diese Asset-Klasse(n) aktualisieren. "
                f"Mehrfach verwendbar. Gültige Werte: {', '.join(AssetClass.values)}"
            ),
        )

    def handle(self, *args, **options):
        async_to_sync(self.handle_async)(*args, **options)

    async def handle_async(self, *args, **options):
        dry_run = options["dry_run"]
        isin_filter = options.get("isin")
        asset_classes = options.get("asset_classes")

        now = timezone.now()
        cutoff = now - PRICE_MAX_AGE

        assets_to_update = await self._get_assets_to_update(isin_filter, asset_classes, cutoff)

        if asset_classes:
            self.stdout.write(f"Filter: Asset-Klassen = {', '.join(asset_classes)}")

        if not assets_to_update:
            self.stdout.write(self.style.SUCCESS("Alle Kurse sind aktuell — nichts zu tun."))
            return

        self.stdout.write(f"{len(assets_to_update)} Asset(s) werden aktualisiert...")

        if dry_run:
            for asset in assets_to_update:
                self.stdout.write(f"DRY {asset.isin} ({asset.asset_class}) würde aktualisiert")
            self.stdout.write(f"\nFertig: 0 aktualisiert, 0 übersprungen, 0 Fehler.")
            return

        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = [
            self._process_asset(asset, now, semaphore)
            for asset in assets_to_update
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ok = errors = skipped = 0

        for asset, result in zip(assets_to_update, results):
            if isinstance(result, Exception):
                self.stdout.write(self.style.ERROR(f"ERR {asset.isin} — {result}"))
                errors += 1
                continue

            status, message = result

            if status == "ok":
                self.stdout.write(self.style.SUCCESS(message))
                ok += 1
            elif status == "skip":
                self.stdout.write(self.style.WARNING(message))
                skipped += 1
            else:
                self.stdout.write(self.style.ERROR(message))
                errors += 1

        self.stdout.write(
            f"\nFertig: {ok} aktualisiert, {skipped} übersprungen, {errors} Fehler."
        )

    async def _process_asset(self, asset: Asset, timestamp, semaphore: asyncio.Semaphore):
        async with semaphore:
            try:
                price = await asyncio.to_thread(
                    self._fetch_price,
                    asset.isin,
                    asset.asset_class,
                )

                if price is None:
                    return ("skip", f"MISS {asset.isin} — Provider lieferte keinen Preis")

                # Sanity-Check: zu starke Abweichung vom letzten bekannten Kurs?
                if asset.current_price is not None:
                    limit = MAX_CHANGE_PERC.get(asset.asset_class, Decimal("25"))
                    change = abs(price - asset.current_price) / asset.current_price * Decimal("100")
                    if change > limit:
                        msg = (
                            f"SUSPICIOUS {asset.isin} — "
                            f"neuer Kurs {price:.4f} weicht {change:.1f}% vom letzten "
                            f"({asset.current_price:.4f}) ab (Limit {limit}%) — nicht gespeichert"
                        )
                        logger.warning(msg)
                        return ("skip", msg)

                await self._save_price(asset, price, timestamp)
                return ("ok", f"OK {asset.isin} — {price:.4f} EUR")

            except Exception as exc:
                return ("error", f"ERR {asset.isin} — {exc}")

    def _fetch_price(self, isin: str, asset_class: str) -> Optional[Decimal]:
        pm = ProviderManager()
        return pm.isin2price(isin, asset_class)

    @sync_to_async
    def _get_assets_to_update(self, isin_filter, asset_classes, cutoff):
        qs = Asset.objects.filter(holdings__quantity__gt=0)
        if isin_filter:
            qs = qs.filter(isin=isin_filter.upper())
        if asset_classes:
            qs = qs.filter(asset_class__in=asset_classes)

        return [
            asset for asset in qs
            if self._needs_update(asset, cutoff)
            and AssetClass.is_valid(asset.asset_class)
        ]

    def _needs_update(self, asset: Asset, cutoff) -> bool:
        if asset.current_price is None:
            return True
        if asset.current_price_timestamp is None:
            return True
        return asset.current_price_timestamp < cutoff

    @sync_to_async
    def _save_price(self, asset: Asset, price: Decimal, timestamp) -> None:
        Price.objects.create(
            asset=asset,
            current_price=price,
            timestamp=timestamp,
        )
