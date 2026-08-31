"""
Manueller Testaufruf für fintech.apis.services.mcp_scalable.ScalableMcpRequest —
bewusst getrennt von update_prices/ProviderManager, solange der neue Provider
noch nicht produktiv eingehängt ist.

Nutzung:
    python manage.py test_scalable_mcp_price US0378331005
"""
from django.core.management.base import BaseCommand, CommandError

from fintech.apis.services.mcp_scalable import ScalableMcpRequest, ScalableMcpNotConnectedError
from fintech.apis.services.request_lib import KeyNotFoundWarning, KeyNotFoundError


class Command(BaseCommand):
    help = "Testet ScalableMcpRequest.isin2price() gegen die MCP-Verbindung, ohne update_prices/ProviderManager zu berühren."

    def add_arguments(self, parser):
        parser.add_argument("isin", help="ISIN, z.B. US0378331005 (Apple)")

    def handle(self, *args, **options):
        isin = options["isin"]
        try:
            price, currency = ScalableMcpRequest().isin2price(isin)
        except ScalableMcpNotConnectedError as exc:
            raise CommandError(f"Nicht verbunden: {exc}")
        except (KeyNotFoundWarning, KeyNotFoundError) as exc:
            raise CommandError(f"Kursabfrage fehlgeschlagen: {exc}")

        self.stdout.write(self.style.SUCCESS(f"{isin}: {price} {currency}"))
