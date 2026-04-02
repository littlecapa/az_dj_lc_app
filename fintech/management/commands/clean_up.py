from asgiref.sync import async_to_sync, sync_to_async
from django.core.management.base import BaseCommand
from fintech.models import Holdings


@sync_to_async
def delete_zero_holdings():
    qs = Holdings.objects.filter(quantity__lte=0)
    isins = list(qs.values_list("asset__isin", flat=True))
    deleted_count, _ = qs.delete()
    return isins, deleted_count


class Command(BaseCommand):
    help = "Löscht Holdings mit Menge <= 0"

    def handle(self, *args, **options):
        async_to_sync(self.handle_async)(*args, **options)

    async def handle_async(self, *args, **options):
        isins, deleted = await delete_zero_holdings()
        self.stdout.write(
            self.style.SUCCESS(f"{deleted} Holdings gelöscht: {isins}")
        )
