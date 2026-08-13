from asgiref.sync import async_to_sync, sync_to_async
from django.core.management.base import BaseCommand
from django.db.models import Max, Count
from django.db.models.functions import TruncDate
from fintech.models import Holdings, Price


@sync_to_async
def delete_zero_holdings():
    # quantity=0 ist seit dem Fonds-Holdings-Look-Through ein gültiger,
    # dauerhafter Zustand (Dummy-Eintrag für Aktien, die nur über einen Fonds
    # gehalten werden) — nur noch echte Negativwerte (Datenfehler) löschen.
    qs = Holdings.objects.filter(quantity__lt=0)
    isins = list(qs.values_list("asset__isin", flat=True))
    deleted_count, _ = qs.delete()
    return isins, deleted_count


@sync_to_async
def deduplicate_prices():
    """
    Für jeden (Asset, Tag) mit mehr als einem Kurseintrag werden alle
    außer dem neuesten (höchste ID) gelöscht.
    """
    # Gruppen finden, die mehr als einen Eintrag pro Tag haben
    groups = (
        Price.objects
        .annotate(date=TruncDate('timestamp'))
        .values('asset_id', 'date')
        .annotate(max_id=Max('id'), count=Count('id'))
        .filter(count__gt=1)
        .order_by()   # Fix von Copilot. Nicht ohne Rücksprache löschen.
    )

    deleted_total = 0
    assets_cleaned = 0

    for g in groups:
        n, _ = (
            Price.objects
            .filter(asset_id=g['asset_id'], timestamp__date=g['date'])
            .exclude(id=g['max_id'])
            .delete()
        )
        deleted_total += n
        if n > 0:
            assets_cleaned += 1

    return deleted_total, assets_cleaned


class Command(BaseCommand):
    help = "Bereinigt die Datenbank: löscht Holdings ≤0 und doppelte Tages-Kurse"

    def handle(self, *args, **options):
        async_to_sync(self.handle_async)(*args, **options)

    async def handle_async(self, *args, **options):
        # 1. Zero-Holdings
        isins, deleted_h = await delete_zero_holdings()
        self.stdout.write(self.style.SUCCESS(
            f"Holdings gelöscht: {deleted_h} ({isins})"
        ))

        # 2. Doppelte Kurs-Einträge
        deleted_p, assets = await deduplicate_prices()
        self.stdout.write(self.style.SUCCESS(
            f"Doppelte Kurseinträge gelöscht: {deleted_p} "
            f"(betrifft {assets} Asset-Tag-Kombinationen)"
        ))
