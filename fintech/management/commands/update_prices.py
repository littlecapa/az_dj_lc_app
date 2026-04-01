"""
Django Management Command: update_prices

Aktualisiert den Kurs aller Assets deren Preis fehlt oder älter als 1h ist.

Aufruf:
    python manage.py update_prices
    python manage.py update_prices --dry-run       # nur anzeigen, nicht speichern
    python manage.py update_prices --isin DE0007164600  # einzelnes Asset
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from fintech.models import Asset, Price
from fintech.models_helper.asset_class import AssetClass
from fintech.apis.services.provider_manager import ProviderManager

PRICE_MAX_AGE = timedelta(hours=1)

# Asset-Klassen-Konfiguration kommt direkt aus AssetClass (models_helper/asset_class.py)

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
        dry_run = options["dry_run"]
        isin_filter = options.get("isin")

        pm = ProviderManager()
        now = timezone.now()
        cutoff = now - PRICE_MAX_AGE

        # --- Assets ermitteln die aktualisiert werden müssen ---
        qs = Asset.objects.all()
        if isin_filter:
            qs = qs.filter(isin=isin_filter.upper())

        assets_to_update = [
            asset for asset in qs
            if self._needs_update(asset, cutoff)
            and AssetClass.is_valid(asset.asset_class)
        ]

        if not assets_to_update:
            self.stdout.write(self.style.SUCCESS("Alle Kurse sind aktuell — nichts zu tun."))
            return

        self.stdout.write(f"{len(assets_to_update)} Asset(s) werden aktualisiert...")

        ok = errors = skipped = 0

        for asset in assets_to_update:
            if dry_run:
                self.stdout.write(f"  DRY   {asset.isin} ({asset.asset_class}) würde aktualisiert")
                continue

            try:
                price: Decimal | None = pm.isin2price(asset.isin, asset.asset_class)

                if price is None:
                    self.stdout.write(
                        self.style.WARNING(f"  MISS  {asset.isin} — Provider lieferte keinen Preis")
                    )
                    errors += 1
                    continue

                self._save_price(asset, price, now)
                self.stdout.write(
                    self.style.SUCCESS(f"  OK    {asset.isin} — {price:.4f} EUR")
                )
                ok += 1

            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  ERR   {asset.isin} — {exc}")
                )
                errors += 1

        if not dry_run:
            self.stdout.write(
                f"\nFertig: {ok} aktualisiert, {skipped} übersprungen, {errors} Fehler."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _needs_update(self, asset: Asset, cutoff) -> bool:
        """True wenn Kurs fehlt oder älter als cutoff."""
        if asset.current_price is None:
            return True
        if asset.current_price_timestamp is None:
            return True
        return asset.current_price_timestamp < cutoff

    def _save_price(self, asset: Asset, price: Decimal, timestamp) -> None:
        """Speichert den Kurs in Price (Historie) und aktualisiert Asset-Cache."""
        # Historischer Eintrag
        Price.objects.create(
            asset=asset,
            current_price=price,
            timestamp=timestamp,
        )
        # Asset-Cache wird automatisch durch Price.save() aktualisiert — siehe models.py