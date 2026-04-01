from django.core.management.base import BaseCommand
from datetime import datetime
from django.utils import timezone
from fintech.models import Asset, Holdings

def delete_zero_holdings():
    qs = Holdings.objects.filter(quantity__lte=0)
    isins = list(qs.values_list("asset__isin", flat=True))
    deleted_count, _ = qs.delete()
    return isins, deleted_count


class Command(BaseCommand):
    help = "Löscht Holdings mit Menge <= 0"

    def handle(self, *args, **options):
        isins, deleted = delete_zero_holdings()
        self.stdout.write(self.style.SUCCESS(
            f"{deleted} Holdings gelöscht: {isins}"
        ))