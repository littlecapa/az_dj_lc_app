"""
Django Management Command: update_etf_holdings

Aktualisiert das FondHolding-Mapping (Aktie <-> Gewicht) für alle gehaltenen
ETFs/Fonds via JustETF-Scraping (Top 10, siehe fintech.apis.services.justetf).

Für eine Top-10-Aktie ohne eigene Holdings-Zeile wird ein Dummy-Eintrag
(quantity=0, average_purchase_price=0) angelegt, damit sie im
Aktien-Look-Through (/fintech/overall-stocks/) mit aktuellem Kurs auftaucht.
In normalen Portfolio-Listen wird sie dank quantity=0 nicht angezeigt.

Schlägt das Speichern eines Dummy-Holdings-Eintrags oder des FondHolding-
Mappings fehl (DB-Fehler o.ä.), wird ein Jira-Bug-Ticket angelegt — der
Lauf wird mit dem nächsten Holding fortgesetzt, nicht abgebrochen.

Aufruf:
python manage.py update_etf_holdings
python manage.py update_etf_holdings --dry-run
python manage.py update_etf_holdings --isin IE00B4L5Y983
"""
import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.jira_client import JiraClient, JiraApiError

from fintech.models import Asset, Holdings, FondHolding
from fintech.models_helper.asset_class import AssetClass
from fintech.apis.services.justetf import JustEtfRequest
from fintech.apis.services.soup_cache import SoupCache
from fintech.apis.services.request_lib import KeyNotFoundWarning

logger = logging.getLogger(__name__)


def _report_save_error(fund, holding_isin, holding_name, error_detail):
    """Legt bei einem Speicherfehler (Dummy-Holdings/FondHolding) ein Jira-Bug-Ticket an."""
    try:
        JiraClient().create_issue(
            summary=f"ETF-Holdings-Update: Speichern fehlgeschlagen ({fund.isin} → {holding_isin})",
            description=(
                f"Beim Speichern eines Fonds-Holdings ist ein Fehler aufgetreten:\n\n"
                f"Fonds: {fund.name} ({fund.isin})\n"
                f"Aktie: {holding_name} ({holding_isin})\n"
                f"Zeitpunkt: {timezone.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                f"Fehler:\n{error_detail}\n\n"
                f"Betroffen: Dummy-Holdings-Eintrag (quantity=0) und/oder FondHolding-Mapping "
                f"für {fund.isin} → {holding_isin}."
            ),
            issue_type="Bug",
        )
    except JiraApiError as exc:
        logger.error(
            f"Jira-Ticket für Speicherfehler {fund.isin} → {holding_isin} "
            f"konnte nicht angelegt werden: {exc}"
        )


class Command(BaseCommand):
    help = "Aktualisiert das FondHolding-Mapping für alle gehaltenen ETFs/Fonds via JustETF (Top 10)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen was passieren würde, nichts speichern.",
        )
        parser.add_argument(
            "--isin",
            type=str,
            help="Nur einen bestimmten Fonds aktualisieren.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        isin_filter = options.get("isin")

        justetf = JustEtfRequest(
            "https://www.justetf.com/de/etf-profile.html?isin={isin}",
            cache=SoupCache(),
            id="update_etf_holdings",
        )

        funds = Asset.objects.filter(
            asset_class__in=[AssetClass.ETF, AssetClass.FOND],
            holdings__quantity__gt=0,
        ).distinct().order_by("name")
        if isin_filter:
            funds = funds.filter(isin=isin_filter.upper())

        if not funds:
            self.stdout.write(self.style.WARNING("Keine gehaltenen ETFs/Fonds gefunden."))
            return

        mappings_upserted = 0
        dummy_created = 0
        errors = 0
        save_errors = 0

        for fund in funds:
            self.stdout.write(f"--- {fund.isin} ({fund.name}) ---")
            try:
                top_holdings = justetf.get_top_holdings(fund.isin)
            except KeyNotFoundWarning:
                self.stdout.write(self.style.ERROR("  Kein ETF-Profil bei JustETF gefunden."))
                errors += 1
                continue
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Fehler beim Abruf: {exc}"))
                errors += 1
                continue

            if not top_holdings:
                self.stdout.write(self.style.WARNING("  Keine Holdings-Daten gefunden."))
                continue

            for h in top_holdings:
                holding_isin = h["isin"]
                if not holding_isin:
                    continue

                if dry_run:
                    exists = Asset.objects.filter(isin=holding_isin).exists()
                    self.stdout.write(
                        f"  DRY {holding_isin} ({h['name']}) {h['percentage']}% "
                        f"[{'Asset existiert' if exists else 'Asset NEU'}]"
                    )
                    continue

                try:
                    with transaction.atomic():
                        asset, _ = Asset.objects.get_or_create(
                            isin=holding_isin,
                            defaults={"name": h["name"], "asset_class": AssetClass.STOCK},
                        )
                        if not Holdings.objects.filter(asset=asset).exists():
                            Holdings.objects.create(
                                asset=asset,
                                quantity=Decimal("0"),
                                average_purchase_price=Decimal("0"),
                            )
                            dummy_created += 1
                            self.stdout.write(f"  Dummy-Holdings angelegt: {holding_isin} ({h['name']})")

                        FondHolding.objects.update_or_create(
                            fund=fund, holding=asset,
                            defaults={"percentage": h["percentage"]},
                        )
                        mappings_upserted += 1
                except Exception as exc:
                    logger.exception(
                        f"Speichern fehlgeschlagen für Fonds-Holding {fund.isin} → {holding_isin}"
                    )
                    self.stdout.write(self.style.ERROR(f"  Speichern fehlgeschlagen: {holding_isin} — {exc}"))
                    save_errors += 1
                    _report_save_error(fund, holding_isin, h["name"], str(exc))

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-Run abgeschlossen — nichts gespeichert."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nFertig: {mappings_upserted} Mapping(s) aktualisiert, "
                f"{dummy_created} Dummy-Holdings neu angelegt, {errors} Abruf-Fehler, "
                f"{save_errors} Speicher-Fehler (Jira-Ticket angelegt)."
            ))
