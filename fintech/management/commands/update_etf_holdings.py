"""
Django Management Command: update_etf_holdings

Aktualisiert das FondHolding-Mapping (Aktie <-> Gewicht) für alle gehaltenen
ETFs/Fonds via JustETF-Scraping (Top 10, siehe fintech.apis.services.justetf).

Für eine Top-10-Aktie ohne eigene Holdings-Zeile wird ein Dummy-Eintrag
(quantity=0, average_purchase_price=0) angelegt, damit sie im
Aktien-Look-Through (/fintech/overall-stocks/) mit aktuellem Kurs auftaucht.
In normalen Portfolio-Listen wird sie dank quantity=0 nicht angezeigt.

Manche ETFs (v.a. "All World"/regionale Mischprodukte) bilden schwer
zugängliche Märkte über einen ANDEREN ETF statt Einzelaktien ab
("Fund-of-Funds"-Konstituente, z.B. ein Indien-ETF als Top-10-Position im
MSCI-AC-World). Solche Einträge werden erkannt (eigenes JustETF-Profil mit
eigener Holdings-Tabelle) und NICHT als Aktie angelegt, sondern übersprungen
— bereits fälschlich als STOCK angelegte Alteinträge werden dabei bereinigt
(asset_class korrigiert, Dummy-Holdings + FondHolding-Mapping entfernt,
außer es handelt sich um eine echte eigene Position mit quantity>0).

Ist bei einem Fonds Asset.holdings_reference gesetzt (z.B. auf "iShares Core
MSCI World"), werden die Holdings von DESSEN JustETF-Seite geholt statt von
der eigenen — sinnvoll für Fonds, die denselben Index abbilden wie ein
anderer gehaltener Fonds (z.B. mehrere "MSCI World"-Tracker verschiedener
Anbieter). Das FondHolding-Mapping wird trotzdem für den tatsächlich
gehaltenen Fonds gespeichert, nur die Datenquelle ändert sich.

Ist bei einem Fonds Asset.ark_ticker gesetzt (z.B. "ARKK"), wird statt der
JustETF-Top-10 die vollständige, tagesaktuelle Holdings-Liste direkt von
ARK Invest verwendet (fintech.apis.services.ark_holdings) — anders als
Wikipedia/companiesmarketcap liefert ARKs CSV eine CUSIP je Position, woraus
sich die ISIN direkt berechnen lässt (ISO 6166). Läuft daher wie ein
normales Get-or-create-per-ISIN, kein Namensabgleich, keine Tail-Erweiterung
nötig — die komplette Liste ersetzt die JustETF-Top-10 für diesen Fonds.

Ist bei einem Fonds Asset.extend_etf gesetzt (nur bei asset_class=ETF
erlaubt, siehe Asset.clean()), werden ZUSÄTZLICH zu den JustETF-Top-10 die
Positionen 11+ einer externen Quelle herangezogen: extend_etf='DAX' nutzt
Wikipedia (de.wikipedia.org/wiki/DAX, alle ~40 mit Gewicht), extend_etf=
'MSCI_WORLD' nutzt companiesmarketcap.com (Positionen 11-50). Beide Quellen
liefern keine ISIN — es werden daher NUR bestehende, im System bereits
bekannte Aktien per Namensabgleich ergänzt (direkt gehalten ODER bereits
über einen anderen Fonds als Dummy-Holdings erfasst), nie neue Assets
angelegt. Läuft deshalb erst NACH der Top-10-Runde aller Fonds (zweiter
Durchlauf über alle Fonds mit gesetztem extend_etf), damit auch Aktien
erfasst werden, die erst in diesem Lauf als Dummy-Holdings neu angelegt
wurden.

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
from fintech.models_helper.etf_extend_source import EtfExtendSource
from fintech.apis.services.justetf import JustEtfRequest
from fintech.apis.services.soup_cache import SoupCache
from fintech.apis.services.request_lib import KeyNotFoundWarning
from fintech.apis.services.wikipedia_dax import get_dax_constituents
from fintech.apis.services.companiesmarketcap import get_holdings as get_companiesmarketcap_holdings
from fintech.apis.services.ark_holdings import get_holdings as get_ark_holdings
from fintech.apis.services.name_matching import match_held_stock

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


def _is_nested_fund(justetf, isin: str) -> bool:
    """
    True, wenn *isin* selbst ein ETF-Profil mit eigener Holdings-Tabelle bei
    JustETF hat — d.h. es ist selbst ein Fonds, keine Einzelaktie (Fund-of-
    Funds-Konstituente). Nutzt denselben Endpunkt wie get_top_holdings, da
    JustETF Aktien- und Fonds-Konstituenten im selben Linkformat
    (/de/stock-profiles/<ISIN>) verlinkt — es gibt kein anderes Unterscheidungs-
    merkmal in den Top-10-Daten selbst.
    """
    try:
        return bool(justetf.get_top_holdings(isin))
    except KeyNotFoundWarning:
        return False
    except Exception as exc:
        logger.warning(f"Fund-of-Funds-Check für {isin} fehlgeschlagen (wird als Aktie behandelt): {exc}")
        return False


def _cleanup_stale_nested_fund_entry(holding_isin: str) -> bool:
    """
    Korrigiert einen Alteintrag aus einem früheren Lauf (vor dieser Fund-of-
    Funds-Erkennung), der fälschlich als STOCK angelegt wurde: asset_class
    wird auf ETF korrigiert, das FondHolding-Mapping entfernt, und der
    Dummy-Holdings-Eintrag gelöscht — aber NIE eine echte Position
    (quantity>0), falls der Nutzer den Fonds selbst direkt hält.
    Gibt True zurück, wenn etwas bereinigt wurde.
    """
    asset = Asset.objects.filter(isin=holding_isin, asset_class=AssetClass.STOCK).first()
    if asset is None:
        return False

    removed_mappings, _ = FondHolding.objects.filter(holding=asset).delete()
    Holdings.objects.filter(asset=asset, quantity=0).delete()

    asset.asset_class = AssetClass.ETF
    asset.save(update_fields=["asset_class"])
    return removed_mappings > 0


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

    def _extend_from_ranked_list(self, fund, label, constituents, tail_start, held_stock_assets, dry_run):
        """
        Ergänzt FondHolding-Mappings aus einer rangierten externen Liste
        (Positionen ab tail_start, 0-indexiert) — nur für Aktien aus
        held_stock_assets (bereits im System bekannt), da diese Quellen keine
        ISIN liefern und daher keine neuen Assets angelegt werden können.
        Gibt (matched_count, error_count) zurück.
        """
        matched = 0
        errors = 0
        for c in constituents[tail_start:]:
            asset = match_held_stock(c["name"], held_stock_assets)
            if asset is None:
                continue

            if dry_run:
                self.stdout.write(
                    f"  DRY {label}-Tail: {c['name']} ({c['symbol']}) {c['percentage']}% "
                    f"→ bereits gehalten: {asset.name} ({asset.isin})"
                )
                matched += 1
                continue

            try:
                FondHolding.objects.update_or_create(
                    fund=fund, holding=asset,
                    defaults={"percentage": c["percentage"]},
                )
                matched += 1
                self.stdout.write(
                    f"  {label}-Tail-Mapping: {c['name']} ({c['symbol']}) {c['percentage']}% "
                    f"→ {asset.name} ({asset.isin})"
                )
            except Exception as exc:
                logger.exception(f"{label}-Tail-Mapping fehlgeschlagen für {fund.isin} → {asset.isin}")
                self.stdout.write(self.style.ERROR(f"  Speichern fehlgeschlagen: {asset.isin} — {exc}"))
                errors += 1
                _report_save_error(fund, asset.isin, asset.name, str(exc))

        return matched, errors

    def _extend_dax_holdings(self, fund, held_stock_assets, dry_run):
        """DAX-Positionen 11+ (Wikipedia). Gibt (matched_count, error_count) zurück."""
        try:
            constituents = get_dax_constituents()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  DAX-Wikipedia-Abruf fehlgeschlagen: {exc}"))
            return 0, 1
        return self._extend_from_ranked_list(fund, "DAX", constituents, 10, held_stock_assets, dry_run)

    def _extend_msci_world_holdings(self, fund, held_stock_assets, dry_run):
        """MSCI-World-Positionen 11-50 (companiesmarketcap.com). Gibt (matched_count, error_count) zurück."""
        try:
            constituents = get_companiesmarketcap_holdings()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  MSCI-World-Holdings-Abruf fehlgeschlagen: {exc}"))
            return 0, 1
        return self._extend_from_ranked_list(fund, "MSCI-World", constituents[:50], 10, held_stock_assets, dry_run)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        isin_filter = options.get("isin")

        justetf = JustEtfRequest(
            "https://www.justetf.com/de/etf-profile.html?isin={isin}",
            cache=SoupCache(),
            id="update_etf_holdings",
        )

        funds = Asset.objects.select_related("holdings_reference").filter(
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
        skipped_nested = 0
        dax_matched = 0
        dax_errors = 0
        msci_world_matched = 0
        msci_world_errors = 0

        # DAX-/MSCI-World-Tail-Erweiterung erst NACH der Top-10-Runde aller Fonds
        # durchführen (zweiter Durchlauf) — sonst würde der Namensabgleich Aktien
        # verpassen, die (a) nur über einen ANDEREN Fonds gehalten werden (Dummy-
        # Holdings quantity=0, z.B. Bayer nur via Xtrackers MSCI Europe Health
        # Care) oder (b) erst in DIESEM Lauf als Dummy-Holdings neu angelegt wurden.
        extend_funds = []

        for fund in funds:
            if fund.ark_ticker:
                self.stdout.write(f"--- {fund.isin} ({fund.name}) — Holdings-Quelle: ARK-CSV ({fund.ark_ticker}) ---")
                try:
                    top_holdings = get_ark_holdings(fund.ark_ticker)
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"  ARK-CSV-Abruf fehlgeschlagen: {exc}"))
                    errors += 1
                    top_holdings = []
            else:
                scrape_isin = fund.holdings_reference.isin if fund.holdings_reference_id else fund.isin
                source_note = f" — Holdings-Quelle: {fund.holdings_reference.name} ({scrape_isin})" if fund.holdings_reference_id else ""
                self.stdout.write(f"--- {fund.isin} ({fund.name}){source_note} ---")
                try:
                    top_holdings = justetf.get_top_holdings(scrape_isin)
                except KeyNotFoundWarning:
                    self.stdout.write(self.style.ERROR("  Kein ETF-Profil bei JustETF gefunden."))
                    errors += 1
                    top_holdings = []
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"  Fehler beim Abruf: {exc}"))
                    errors += 1
                    top_holdings = []

            if not top_holdings:
                self.stdout.write(self.style.WARNING("  Keine Holdings-Daten gefunden."))

            for h in top_holdings:
                holding_isin = h["isin"]
                if not holding_isin:
                    continue

                if _is_nested_fund(justetf, holding_isin):
                    skipped_nested += 1
                    if dry_run:
                        self.stdout.write(self.style.WARNING(
                            f"  DRY {holding_isin} ({h['name']}) ist selbst ein Fonds "
                            f"(Fund-of-Funds) — würde übersprungen."
                        ))
                        continue
                    self.stdout.write(self.style.WARNING(
                        f"  Übersprungen: {holding_isin} ({h['name']}) ist selbst ein Fonds, "
                        f"keine Einzelaktie."
                    ))
                    if _cleanup_stale_nested_fund_entry(holding_isin):
                        self.stdout.write(self.style.WARNING(
                            f"    Alteintrag bereinigt: {holding_isin} war fälschlich als STOCK angelegt."
                        ))
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

            if fund.extend_etf in (EtfExtendSource.DAX, EtfExtendSource.MSCI_WORLD):
                extend_funds.append(fund)

        if extend_funds:
            # Jetzt alle inzwischen bekannten Aktien als Basis nehmen — auch
            # Dummy-Holdings (quantity=0), egal ob aus einem früheren Lauf oder
            # gerade eben oben in der Top-10-Runde neu angelegt.
            held_stock_assets = list(
                Asset.objects.filter(asset_class=AssetClass.STOCK, holdings__isnull=False).distinct()
            )
            self.stdout.write(
                f"\n{len(held_stock_assets)} bekannte Aktie(n) (direkt oder über einen Fonds) "
                f"als Basis für DAX-/MSCI-World-Tail-Namensabgleich."
            )

            for fund in extend_funds:
                self.stdout.write(f"--- Tail-Erweiterung: {fund.isin} ({fund.name}) ---")
                if fund.extend_etf == EtfExtendSource.DAX:
                    self.stdout.write("  DAX-Tail-Erweiterung aktiv (extend_etf=DAX) …")
                    n, e = self._extend_dax_holdings(fund, held_stock_assets, dry_run)
                    self.stdout.write(f"  DAX-Tail-Erweiterung: {n} Treffer, {e} Fehler.")
                    dax_matched += n
                    dax_errors += e

                elif fund.extend_etf == EtfExtendSource.MSCI_WORLD:
                    self.stdout.write("  MSCI-World-Tail-Erweiterung aktiv (extend_etf=MSCI_WORLD) …")
                    n, e = self._extend_msci_world_holdings(fund, held_stock_assets, dry_run)
                    self.stdout.write(f"  MSCI-World-Tail-Erweiterung: {n} Treffer, {e} Fehler.")
                    msci_world_matched += n
                    msci_world_errors += e

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"Dry-Run abgeschlossen — nichts gespeichert. "
                f"{skipped_nested} Fund-of-Funds-Konstituente(n) würden übersprungen, "
                f"{dax_matched} DAX-Tail-Treffer, {msci_world_matched} MSCI-World-Tail-Treffer "
                f"(jeweils Positionen 11+) gefunden."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nFertig: {mappings_upserted} Mapping(s) aktualisiert, "
                f"{dummy_created} Dummy-Holdings neu angelegt, {skipped_nested} Fund-of-Funds-"
                f"Konstituente(n) übersprungen, {dax_matched} DAX-Tail-Mapping(s) + "
                f"{msci_world_matched} MSCI-World-Tail-Mapping(s) ergänzt, "
                f"{errors} Abruf-Fehler, {save_errors + dax_errors + msci_world_errors} "
                f"Speicher-Fehler (Jira-Ticket angelegt)."
            ))
