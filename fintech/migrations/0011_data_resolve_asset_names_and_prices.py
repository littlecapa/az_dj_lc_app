"""
Data migration 0011

Zwei Bereinigungen die beim initialen Befüllen über die API entstehen können:

1. Asset-Namen auflösen
   Alle Assets bei denen name == isin (d.h. kein richtiger Name gesetzt wurde)
   werden über Yahoo Finance nachgeschlagen und aktualisiert.

2. WatchlistEntry.price_at_add nachfüllen
   Wenn beim Eintragen in die Watchlist noch kein Kurs gecacht war, bleibt
   price_at_add None. Hier wird dann asset.current_price als Fallback gesetzt,
   damit die Performance-Seite rechnen kann.

Beide Schritte sind best-effort: externe API-Fehler werden geloggt aber
brechen die Migration nicht ab.
"""

import logging
from django.db import migrations

logger = logging.getLogger(__name__)


def resolve_asset_names(apps, schema_editor):
    """Holt fehlende Asset-Namen von Yahoo Finance."""
    Asset = apps.get_model("fintech", "Asset")
    nameless = [a for a in Asset.objects.all() if a.name == a.isin]

    if not nameless:
        logger.info("resolve_asset_names: keine Assets ohne Namen gefunden")
        return

    logger.info(f"resolve_asset_names: {len(nameless)} Asset(s) zum Aktualisieren")

    # Import hier damit die Migration nicht scheitert wenn das Modul fehlt
    try:
        from fintech.apis.services.yahoo_finance import YahooFinanceRequest
        from fintech.apis.services.request_lib import KeyNotFoundWarning
        yahoo = YahooFinanceRequest()
    except ImportError as exc:
        logger.error(f"resolve_asset_names: Import fehlgeschlagen — übersprungen: {exc}")
        return

    updated = failed = 0
    for asset in nameless:
        try:
            new_name = yahoo.isin2name(asset.isin)
            asset.name = new_name
            asset.save()
            updated += 1
            logger.info(f"  {asset.isin}: Name gesetzt → '{new_name}'")
        except Exception as exc:
            failed += 1
            logger.warning(f"  {asset.isin}: Name-Abruf fehlgeschlagen — {exc}")

    logger.info(f"resolve_asset_names: {updated} aktualisiert, {failed} fehlgeschlagen")


def fill_missing_price_at_add(apps, schema_editor):
    """Setzt price_at_add aus asset.current_price wenn noch nicht gesetzt."""
    WatchlistEntry = apps.get_model("fintech", "WatchlistEntry")
    missing = WatchlistEntry.objects.filter(price_at_add__isnull=True).select_related("asset")

    count = missing.count()
    if count == 0:
        logger.info("fill_missing_price_at_add: alle Einträge haben bereits einen Einstandskurs")
        return

    logger.info(f"fill_missing_price_at_add: {count} Einträge ohne price_at_add")

    updated = skipped = 0
    for entry in missing:
        if entry.asset.current_price:
            entry.price_at_add = entry.asset.current_price
            entry.save()
            updated += 1
            logger.info(f"  {entry.asset.isin} in '{entry.watchlist_id}': price_at_add = {entry.asset.current_price}")
        else:
            skipped += 1
            logger.warning(f"  {entry.asset.isin}: kein current_price vorhanden — übersprungen")

    logger.info(f"fill_missing_price_at_add: {updated} gesetzt, {skipped} übersprungen (kein Kurs)")


def noop(apps, schema_editor):
    """Rückwärts-Migration: nichts zurücksetzen (Datenverlust wäre unerwünscht)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0010_watchlistentry_source_price_nullable"),
    ]

    operations = [
        migrations.RunPython(resolve_asset_names,      noop),
        migrations.RunPython(fill_missing_price_at_add, noop),
    ]
