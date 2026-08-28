"""
Django Management Command: update_prices

Aktualisiert den Kurs aller Assets deren Preis fehlt oder älter als 1h ist.

Aufruf:
python manage.py update_prices
python manage.py update_prices --dry-run
python manage.py update_prices --isin DE0007164600
python manage.py update_prices --isin DE0007164600 --force
python manage.py update_prices --asset-class STOCK
python manage.py update_prices --asset-class ETF --asset-class ETC
"""

import asyncio
import logging
from datetime import timedelta
from typing import Optional
from decimal import Decimal

from asgiref.sync import async_to_sync, sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django.db.models import Q
from fintech.models import Asset, Price
from fintech.models_helper.asset_class import AssetClass
from fintech.apis.services.provider_manager import ProviderManager
from fintech.services import flag_price_fetch_failure, clear_price_fetch_failure, report_price_fetch_failures

logger = logging.getLogger(__name__)

PRICE_MAX_AGE = timedelta(hours=1)
CONCURRENCY = 10

# Ein Kurs, der den Plausibilitäts-Check (MAX_CHANGE_PERC) verfehlt, wird erst
# gespeichert, wenn derselbe (± Toleranz) Wert über diese Dauer hinweg
# konsistent gemeldet wird — ein einmaliger Scraping-Fehler liefert bei jedem
# Lauf einen anderen zufälligen Wert, ein echter Kurssprung (Split, Rallye,
# Crash) bestätigt sich dagegen von Lauf zu Lauf.
SUSPICIOUS_PRICE_CONFIRM_THRESHOLD = timedelta(hours=24)
SUSPICIOUS_PRICE_TOLERANCE = Decimal("0.02")  # 2 %

# Maximale erlaubte Tagesveränderung pro Asset-Klasse (in %).
# Preise die stärker abweichen werden als Scraping-Fehler gewertet und verworfen.
MAX_CHANGE_PERC: dict[str, Decimal] = {
    AssetClass.ETF:        Decimal("10"),
    AssetClass.ETC:        Decimal("10"),
    AssetClass.FOND:       Decimal("10"),
    AssetClass.STOCK:      Decimal("25"),  # temporär erhöht (war 8%)
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
            "--force",
            action="store_true",
            help=(
                "Nur zusammen mit --isin: Plausibilitäts-Check und "
                "suspicious-price-Tracking für dieses eine Asset überspringen, "
                "neuen Kurs sofort übernehmen (z.B. nach manuell verifiziertem "
                "Split/Kurssprung, der sonst erst nach 24h automatisch bestätigt würde)."
            ),
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
        force = options.get("force", False)

        if force and not isin_filter:
            raise CommandError("--force ist nur zusammen mit --isin erlaubt.")

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
            self._process_asset(asset, now, semaphore, force=force)
            for asset in assets_to_update
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ok = errors = skipped = 0
        failures = []

        for asset, result in zip(assets_to_update, results):
            if isinstance(result, Exception):
                self.stdout.write(self.style.ERROR(f"ERR {asset.isin} — {result}"))
                errors += 1
                continue

            status, message, failure_detail = result

            if status == "ok":
                self.stdout.write(self.style.SUCCESS(message))
                ok += 1
            elif status == "skip":
                self.stdout.write(self.style.WARNING(message))
                skipped += 1
            else:
                self.stdout.write(self.style.ERROR(message))
                errors += 1
                if failure_detail:
                    failures.append(failure_detail)

        if failures:
            await asyncio.to_thread(report_price_fetch_failures, failures)
            self.stdout.write(f"Sammel-Jira-Ticket für {len(failures)} fehlgeschlagene Kurs-Abrufe angelegt.")

        self.stdout.write(
            f"\nFertig: {ok} aktualisiert, {skipped} übersprungen, {errors} Fehler."
        )

    async def _process_asset(self, asset: Asset, timestamp, semaphore: asyncio.Semaphore, force: bool = False):
        async with semaphore:
            try:
                price = await asyncio.to_thread(
                    self._fetch_price,
                    asset.isin,
                    asset.asset_class,
                    asset.yahoo_symbol,
                )
            except Exception as exc:
                # Abruf-Fehler: erst ab 24h ununterbrochenem Fehlschlag wird
                # price_fetch_blocked gesetzt und escalated=True zurückgegeben.
                # Kein Ticket hier — der Aufrufer sammelt alle eskalierten Fehler
                # des Laufs und meldet sie gebündelt (ein zentraler Ausfall wie
                # Comdirect down soll EIN Ticket ergeben, nicht eins pro Asset,
                # und ein einzelner Hänger soll gar keins ergeben).
                escalated = await asyncio.to_thread(flag_price_fetch_failure, asset, str(exc))
                suffix = " (price_fetch_blocked gesetzt)" if escalated else " (wird erneut versucht)"
                return (
                    "error",
                    f"ERR {asset.isin} — {exc}{suffix}",
                    {"isin": asset.isin, "name": asset.name, "asset_class": asset.asset_class, "error": str(exc)}
                    if escalated else None,
                )

            if price is None:
                error_detail = "Alle Kursquellen lieferten keinen Preis (isin2price → None)."
                escalated = await asyncio.to_thread(flag_price_fetch_failure, asset, error_detail)
                suffix = " (price_fetch_blocked gesetzt)" if escalated else " (wird erneut versucht)"
                return (
                    "error",
                    f"ERR {asset.isin} — kein Kurs verfügbar{suffix}",
                    {"isin": asset.isin, "name": asset.name, "asset_class": asset.asset_class, "error": error_detail}
                    if escalated else None,
                )

            try:
                # Sanity-Check: zu starke Abweichung vom letzten bekannten Kurs?
                # (Preis wurde geliefert, wird aber als unplausibel verworfen — kein
                # Abruf-Fehler, daher kein price_fetch_blocked/Ticket. Nächster Lauf
                # versucht es erneut.)
                if asset.current_price is not None and not force:
                    limit = MAX_CHANGE_PERC.get(asset.asset_class, Decimal("25"))
                    change = abs(price - asset.current_price) / asset.current_price * Decimal("100")
                    if change > limit:
                        confirmed = await self._check_suspicious_price(asset, price)
                        if not confirmed:
                            msg = (
                                f"SUSPICIOUS {asset.isin} — "
                                f"neuer Kurs {price:.4f} weicht {change:.1f}% vom letzten "
                                f"({asset.current_price:.4f}) ab (Limit {limit}%) — nicht gespeichert"
                            )
                            logger.warning(msg)
                            return ("skip", msg, None)
                        logger.warning(
                            f"CONFIRMED {asset.isin} — Kurs {price:.4f} seit "
                            f"{SUSPICIOUS_PRICE_CONFIRM_THRESHOLD} konsistent trotz {change:.1f}% "
                            f"Abweichung vom alten Kurs ({asset.current_price:.4f}) — wird jetzt übernommen."
                        )

                await self._save_price(asset, price, timestamp)
                await asyncio.to_thread(clear_price_fetch_failure, asset)
                return ("ok", f"OK {asset.isin} — {price:.4f} EUR", None)

            except Exception as exc:
                return ("error", f"ERR {asset.isin} — {exc}", None)

    def _fetch_price(self, isin: str, asset_class: str, yahoo_symbol: Optional[str] = None) -> Optional[Decimal]:
        pm = ProviderManager()
        return pm.isin2price(isin, asset_class, yahoo_symbol=yahoo_symbol)

    @sync_to_async
    def _get_assets_to_update(self, isin_filter, asset_classes, cutoff):
        # Kurse holen für: alle Holdings (auch quantity=0 — Dummy-Einträge für
        # Aktien, die nur über einen Fonds gehalten werden, brauchen trotzdem
        # einen aktuellen Kurs für den Look-Through) ODER Assets in einer
        # Watchlist — blockierte Assets (offenes Jira-Ticket) werden übersprungen.
        qs = Asset.objects.filter(
            Q(holdings__isnull=False) | Q(watchlistentry__isnull=False)
        ).exclude(price_fetch_blocked=True).distinct()
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
        if asset.suspicious_price is not None:
            asset.suspicious_price = None
            asset.suspicious_price_since = None
            asset.save(update_fields=["suspicious_price", "suspicious_price_since"])

    @sync_to_async
    def _check_suspicious_price(self, asset: Asset, price: Decimal) -> bool:
        """
        Trackt einen wegen zu großer Abweichung verworfenen Kurs. Bleibt der
        neue Kurs über SUSPICIOUS_PRICE_CONFIRM_THRESHOLD hinweg konsistent
        (innerhalb SUSPICIOUS_PRICE_TOLERANCE) statt bei jedem Lauf zufällig
        anders zu sein, gilt er als echter Kurssprung (Split, Rallye, Crash)
        statt als einmaliger Scraping-Fehler.

        Gibt True zurück, wenn der Kurs jetzt zur Übernahme freigegeben ist
        (Aufrufer speichert ihn dann ganz normal), sonst False.
        """
        now = timezone.now()

        if asset.suspicious_price is not None:
            deviation = abs(price - asset.suspicious_price) / asset.suspicious_price
            if deviation <= SUSPICIOUS_PRICE_TOLERANCE:
                if now - asset.suspicious_price_since >= SUSPICIOUS_PRICE_CONFIRM_THRESHOLD:
                    return True
                return False

        # Erster oder gegenüber dem bisherigen Tracking abweichender
        # "suspicious" Kurs — Tracking (neu) starten.
        asset.suspicious_price = price
        asset.suspicious_price_since = now
        asset.save(update_fields=["suspicious_price", "suspicious_price_since"])
        return False
