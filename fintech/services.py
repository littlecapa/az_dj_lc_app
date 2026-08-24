"""
Gemeinsame Business-Logik für Asset-Anlage mit Kurs-Abruf.

Wird sowohl vom Watchlist-API-Endpoint (apis/watchlist_api.py) als auch vom
Watchlist-Import (views.watchlist_import) verwendet, damit ein neues Asset nie
ohne aktuellen Kurs angelegt wird — schlägt der Kurs-Abruf fehl, wird nichts
gespeichert.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from typing import NamedTuple, Optional

from django.db import transaction
from django.utils import timezone

from core.jira_client import JiraClient, JiraApiError

from .apis.services.provider_manager import ProviderManager
from .models import Asset, Price

logger = logging.getLogger(__name__)

_provider_manager = ProviderManager()

# Ein einzelner fehlgeschlagener Abruf (z.B. kurzer Provider-Hänger) soll noch
# kein Ticket auslösen. Erst wenn ein Asset ununterbrochen länger als diese
# Dauer fehlschlägt, wird price_fetch_blocked gesetzt und gemeldet.
PRICE_FETCH_FAILURE_THRESHOLD = timedelta(hours=24)


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


def refresh_asset_price(asset: Asset, failures: Optional[list] = None) -> Optional[Decimal]:
    """Holt aktiv den aktuellen Kurs für ein bestehendes Asset und speichert ihn.

    Ist asset.price_fetch_blocked gesetzt, wird gar nicht erst versucht. Schlägt der
    Abruf fehl, wird das Flag gesetzt (siehe flag_price_fetch_failure) und — falls
    *failures* übergeben wurde — ein Eintrag angehängt, den der Aufrufer am Ende
    seines Laufs gebündelt per report_price_fetch_failures() meldet.

    Gibt den neuen Kurs zurück, oder None (blockiert oder Fehler).
    """
    if asset.price_fetch_blocked:
        logger.info(f"Kurs-Abruf für {asset.isin} übersprungen (price_fetch_blocked=True)")
        return None

    try:
        price = _provider_manager.isin2price(asset.isin, asset.asset_class)
    except Exception as exc:
        logger.warning(f"Kurs-Abruf für {asset.isin} fehlgeschlagen: {exc}")
        escalated = flag_price_fetch_failure(asset, str(exc))
        if escalated and failures is not None:
            failures.append(_failure_entry(asset, str(exc)))
        return None

    if price is None:
        error_detail = "Alle Kursquellen lieferten keinen Preis (isin2price → None)."
        logger.warning(f"Kurs-Abruf für {asset.isin} lieferte keinen Kurs")
        escalated = flag_price_fetch_failure(asset, error_detail)
        if escalated and failures is not None:
            failures.append(_failure_entry(asset, error_detail))
        return None

    Price.objects.create(asset=asset, current_price=price, timestamp=timezone.now())
    clear_price_fetch_failure(asset)
    if asset.suspicious_price is not None:
        asset.suspicious_price = None
        asset.suspicious_price_since = None
        asset.save(update_fields=["suspicious_price", "suspicious_price_since"])
    return price


def flag_price_fetch_failure(asset: Asset, error_detail: str) -> bool:
    """
    Registriert einen fehlgeschlagenen Kurs-Abruf für *asset*.

    Beim ersten Fehlschlag wird nur price_fetch_failing_since gesetzt — noch KEIN
    price_fetch_blocked, noch kein Ticket. Erst wenn seit diesem ersten Fehlschlag
    mehr als PRICE_FETCH_FAILURE_THRESHOLD vergangen ist, wird price_fetch_blocked
    gesetzt. Legt selbst KEIN Jira-Ticket an — der Aufrufer sammelt die eskalierten
    Fehler über einen ganzen Lauf hinweg und meldet sie gebündelt über
    report_price_fetch_failures(), damit ein zentraler Ausfall (z. B. Comdirect
    nicht erreichbar) nicht ein Ticket pro betroffenem Asset erzeugt.

    Solange price_fetch_blocked gesetzt bleibt, überspringen refresh_asset_price()
    und update_prices weitere Abrufversuche für dieses Asset.

    Gibt True zurück, wenn das Asset durch diesen Aufruf gerade neu blockiert
    wurde (Signal für den Aufrufer, es fürs Jira-Ticket zu melden).
    """
    now = timezone.now()

    if asset.price_fetch_failing_since is None:
        asset.price_fetch_failing_since = now
        asset.save(update_fields=["price_fetch_failing_since"])
        logger.info(
            f"Kurs-Abruf für {asset.isin} fehlgeschlagen (erster Fehlschlag, "
            f"noch nicht blockiert): {error_detail}"
        )
        return False

    if asset.price_fetch_blocked:
        return False

    if now - asset.price_fetch_failing_since >= PRICE_FETCH_FAILURE_THRESHOLD:
        asset.price_fetch_blocked = True
        asset.save(update_fields=["price_fetch_blocked"])
        logger.warning(
            f"Kurs-Abruf für {asset.isin} schlägt seit über 24h fehl — "
            f"price_fetch_blocked gesetzt: {error_detail}"
        )
        return True

    return False


def clear_price_fetch_failure(asset: Asset) -> None:
    """Setzt price_fetch_failing_since nach einem erfolgreichen Kurs-Abruf zurück."""
    if asset.price_fetch_failing_since is not None:
        asset.price_fetch_failing_since = None
        asset.save(update_fields=["price_fetch_failing_since"])


def _failure_entry(asset: Asset, error_detail: str) -> dict:
    return {
        "isin": asset.isin,
        "name": asset.name,
        "asset_class": asset.asset_class,
        "error": error_detail,
    }


def report_price_fetch_failures(failures: list) -> None:
    """
    Legt EIN Jira-Bug-Ticket an, das alle in einem Lauf fehlgeschlagenen
    Kurs-Abrufe auflistet (statt eines Tickets pro Asset). No-op bei leerer Liste.

    failures: Liste von dicts {"isin", "name", "asset_class", "error"}
    (siehe _failure_entry).
    """
    if not failures:
        return

    lines = "\n".join(
        f"- {f['name']} ({f['isin']}, {f['asset_class']}): {f['error']}"
        for f in failures
    )
    try:
        JiraClient().create_issue(
            summary=f"Kurs-Abruf fehlgeschlagen für {len(failures)} Asset(s)",
            description=(
                f"Für folgende {len(failures)} Asset(s) konnte kein aktueller Kurs "
                f"ermittelt werden:\n\n{lines}\n\n"
                f"Zeitpunkt: {timezone.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                f"price_fetch_blocked wurde für alle betroffenen Assets automatisch auf "
                f"True gesetzt — weitere automatische Abrufversuche sind pausiert, bis das "
                f"Feld manuell wieder auf False gesetzt wird (Django-Admin oder "
                f"/fintech/clean_up/ → Remove Price Fetch Blocker)."
            ),
            issue_type="Bug",
        )
        logger.info(f"Sammel-Jira-Ticket für {len(failures)} fehlgeschlagene Kurs-Abrufe angelegt.")
    except JiraApiError as exc:
        logger.error(
            f"Sammel-Jira-Ticket für {len(failures)} fehlgeschlagene Kurs-Abrufe "
            f"konnte nicht angelegt werden: {exc}"
        )
