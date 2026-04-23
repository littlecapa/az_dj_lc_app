"""
Django Management Command: update_prices

Aktualisiert den Kurs aller Assets deren Preis fehlt oder älter als 1h ist.

Aufruf:
python manage.py update_prices
python manage.py update_prices --dry-run
python manage.py update_prices --isin DE0007164600
"""

import asyncio
from datetime import timedelta
from typing import Optional
from decimal import Decimal

from asgiref.sync import async_to_sync, sync_to_async
from django.core.management.base import BaseCommand
from django.utils import timezone

from fintech.models import Asset, Price
from fintech.models_helper.asset_class import AssetClass
from fintech.apis.services.provider_manager import ProviderManager

PRICE_MAX_AGE = timedelta(hours=1)
CONCURRENCY = 10


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

    def handle(self, *args, **options):
        async_to_sync(self.handle_async)(*args, **options)

    async def handle_async(self, *args, **options):
        dry_run = options["dry_run"]
        isin_filter = options.get("isin")

        now = timezone.now()
        cutoff = now - PRICE_MAX_AGE

        assets_to_update = await self._get_assets_to_update(isin_filter, cutoff)

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
        price = None
        async with semaphore:
            try:
                price = await asyncio.to_thread(
                    self._fetch_price,
                    asset.isin,
                    asset.asset_class,
                )

                if price is None:
                    return ("skip", f"MISS {asset.isin} — Provider lieferte keinen Preis")

                await self._save_price(asset, price, timestamp)
                return ("ok", f"OK {asset.isin} — {price:.4f} EUR")

            except Exception as exc:
                return ("error", f"ERR {asset.isin} — {exc}")

    def _fetch_price(self, isin: str, asset_class: str) -> Optional[Decimal]:
        pm = ProviderManager()
        return pm.isin2price(isin, asset_class)

    @sync_to_async
    def _get_assets_to_update(self, isin_filter, cutoff):
        qs = Asset.objects.all()
        if isin_filter:
            qs = qs.filter(isin=isin_filter.upper())

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
