"""
Migration 0044: PC Partner Group als weitere "manuell erfasst"-Position
(EM Digital Leaders) — analog zu Migration 0043, als Watchlist-Eintrag in
"Fonds-Ergänzungen".

ISIN recherchiert (onvista-Suche): KYG6956A1013 (Cayman-Islands-Gesellschaft,
Ticker PCT, HD-,10-Notation passend zum Factsheet-Eintrag "PC Partner Group
Ltd. Registered Shares HD -,10").
"""
from django.db import migrations

WATCHLIST_NAME = "Fonds-Ergänzungen"
ISIN = "KYG6956A1013"
NAME = "PC Partner Group Ltd."


def add_asset_and_watchlist_entry(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    Watchlist = apps.get_model('fintech', 'Watchlist')
    WatchlistEntry = apps.get_model('fintech', 'WatchlistEntry')
    User = apps.get_model('auth', 'User')

    user = User.objects.filter(is_superuser=True).order_by('id').first()

    asset, _ = Asset.objects.get_or_create(
        isin=ISIN,
        defaults={'name': NAME, 'asset_class': 'STOCK'},
    )
    if user is not None:
        watchlist, _ = Watchlist.objects.get_or_create(name=WATCHLIST_NAME, user=user)
        WatchlistEntry.objects.get_or_create(watchlist=watchlist, asset=asset)


def remove_watchlist_entry(apps, schema_editor):
    Watchlist = apps.get_model('fintech', 'Watchlist')
    WatchlistEntry = apps.get_model('fintech', 'WatchlistEntry')
    watchlist = Watchlist.objects.filter(name=WATCHLIST_NAME).first()
    if watchlist is not None:
        WatchlistEntry.objects.filter(watchlist=watchlist, asset__isin=ISIN).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0043_new_stocks_from_manual_fund_holdings'),
    ]

    operations = [
        migrations.RunPython(add_asset_and_watchlist_entry, remove_watchlist_entry),
    ]
