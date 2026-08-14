"""
Migration 0045: Nu Holdings als weitere "manuell erfasst"-Position
(EM Digital Leaders) — analog zu Migration 0043/0044, als Watchlist-Eintrag
in "Fonds-Ergänzungen".

ISIN recherchiert (onvista-Suche): KYG6683N1034 (Cayman-Islands-Gesellschaft,
Ticker NU, passend zum Factsheet-Eintrag "Nu Holdings Ltd. Reg.Shares Cl.A
DL-,000066").
"""
from django.db import migrations

WATCHLIST_NAME = "Fonds-Ergänzungen"
ISIN = "KYG6683N1034"
NAME = "Nu Holdings Ltd."


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
        ('fintech', '0044_pc_partner_group_manual_holding'),
    ]

    operations = [
        migrations.RunPython(add_asset_and_watchlist_entry, remove_watchlist_entry),
    ]
