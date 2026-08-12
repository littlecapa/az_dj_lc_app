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

from core.jira_client import JiraClient, JiraApiError

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

    Ist asset.price_fetch_blocked gesetzt, wird gar nicht erst versucht (verhindert
    Jira-Ticket-Duplikate). Schlägt der Abruf fehl, wird das Flag gesetzt und ein
    Jira-Bug-Ticket angelegt (siehe flag_price_fetch_failure).

    Gibt den neuen Kurs zurück, oder None (blockiert oder Fehler).
    """
    if asset.price_fetch_blocked:
        logger.info(f"Kurs-Abruf für {asset.isin} übersprungen (price_fetch_blocked=True)")
        return None

    try:
        price = _provider_manager.isin2price(asset.isin, asset.asset_class)
    except Exception as exc:
        logger.warning(f"Kurs-Abruf für {asset.isin} fehlgeschlagen: {exc}")
        flag_price_fetch_failure(asset, str(exc))
        return None

    if price is None:
        logger.warning(f"Kurs-Abruf für {asset.isin} lieferte keinen Kurs")
        flag_price_fetch_failure(asset, "Alle Kursquellen lieferten keinen Preis (isin2price → None).")
        return None

    Price.objects.create(asset=asset, current_price=price, timestamp=timezone.now())
    return price


def flag_price_fetch_failure(asset: Asset, error_detail: str) -> None:
    """
    Setzt asset.price_fetch_blocked und legt ein Jira-Bug-Ticket mit den
    Fehlerdetails an. Solange das Flag gesetzt bleibt, überspringen
    refresh_asset_price() und update_prices weitere Abrufversuche für dieses
    Asset — verhindert Ticket-Duplikate bei wiederholten Fehlschlägen.

    Schlägt die Jira-Anfrage selbst fehl (z. B. falsch konfiguriert), wird das
    nur geloggt — das Flag bleibt in jedem Fall gesetzt.
    """
    asset.price_fetch_blocked = True
    asset.save(update_fields=["price_fetch_blocked"])

    try:
        JiraClient().create_issue(
            summary=f"Kurs-Abruf fehlgeschlagen: {asset.name} ({asset.isin})",
            description=(
                f"Für folgendes Asset konnte kein aktueller Kurs ermittelt werden:\n\n"
                f"Name: {asset.name}\n"
                f"ISIN: {asset.isin}\n"
                f"Asset-Klasse: {asset.asset_class}\n"
                f"Zeitpunkt: {timezone.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                f"Fehler:\n{error_detail}\n\n"
                f"price_fetch_blocked wurde automatisch auf True gesetzt — weitere "
                f"automatische Abrufversuche sind für dieses Asset pausiert, bis das "
                f"Feld im Django-Admin (Asset → {asset.isin}) manuell wieder auf False "
                f"gesetzt wird."
            ),
            issue_type="Bug",
        )
    except JiraApiError as exc:
        logger.error(f"Jira-Ticket für fehlgeschlagenen Kurs-Abruf {asset.isin} konnte nicht angelegt werden: {exc}")
