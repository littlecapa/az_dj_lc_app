"""
Gemeinsame Business-Logik für Asset-Anlage mit Kurs-Abruf.

Wird sowohl vom Watchlist-API-Endpoint (apis/watchlist_api.py) als auch vom
Watchlist-Import (views.watchlist_import) verwendet, damit ein neues Asset nie
ohne aktuellen Kurs angelegt wird — schlägt der Kurs-Abruf fehl, wird nichts
gespeichert.
"""
import logging
from decimal import Decimal
from typing import NamedTuple, Optional

from django.db import transaction
from django.utils import timezone

from .apis.services.provider_manager import ProviderManager
from .models import Asset, Price

logger = logging.getLogger(__name__)

_provider_manager = ProviderManager()


class AssetResolution(NamedTuple):
    asset: Optional[Asset]
    created: bool
    price: Optional[Decimal]
    error: Optional[str]


def resolve_asset_with_price(isin: str, name: str, asset_class: str, dry_run: bool = False) -> AssetResolution:
    """
    Liefert das bestehende Asset zu *isin*, oder legt bei einem neuen Asset nur
    dann eines an, wenn zuvor ein aktueller Kurs erfolgreich abgerufen wurde.

    - Asset existiert bereits: wird unverändert zurückgegeben (kein Kurs-Abruf).
    - Asset ist neu und Kurs-Abruf schlägt fehl: asset=None, error gesetzt,
      es wird NICHTS in der DB angelegt.
    - Asset ist neu, Kurs-Abruf erfolgreich, dry_run=True: nichts wird
      gespeichert, aber created=True und price sind gesetzt (Vorschau).
    - Asset ist neu, Kurs-Abruf erfolgreich, dry_run=False: Asset + Price
      werden angelegt.
    """
    existing = Asset.objects.filter(isin=isin).first()
    if existing:
        return AssetResolution(existing, False, existing.current_price, None)

    try:
        price = _provider_manager.isin2price(isin, asset_class)
    except Exception as exc:
        logger.warning(f"Kurs-Abruf für neues Asset {isin} fehlgeschlagen: {exc}")
        return AssetResolution(None, False, None, f"Kurs-Abruf fehlgeschlagen: {exc}")

    if price is None:
        logger.warning(f"Kurs-Abruf für neues Asset {isin} lieferte keinen Kurs")
        return AssetResolution(None, False, None, "Kein Kurs verfügbar (alle Kursquellen fehlgeschlagen)")

    if dry_run:
        return AssetResolution(None, True, price, None)

    with transaction.atomic():
        asset = Asset.objects.create(isin=isin, name=name, asset_class=asset_class)
        Price.objects.create(asset=asset, current_price=price, timestamp=timezone.now())
    asset.refresh_from_db()
    logger.info(f"Neues Asset angelegt: {isin} ({name}) @ {price}")
    return AssetResolution(asset, True, asset.current_price, None)


def refresh_asset_price(asset: Asset) -> Optional[Decimal]:
    """Holt aktiv den aktuellen Kurs für ein bestehendes Asset und speichert ihn.

    Gibt den neuen Kurs zurück, oder None wenn der Abruf fehlschlägt.
    """
    try:
        price = _provider_manager.isin2price(asset.isin, asset.asset_class)
    except Exception as exc:
        logger.warning(f"Kurs-Abruf für {asset.isin} fehlgeschlagen: {exc}")
        return None

    if price is None:
        logger.warning(f"Kurs-Abruf für {asset.isin} lieferte keinen Kurs")
        return None

    Price.objects.create(asset=asset, current_price=price, timestamp=timezone.now())
    return price
