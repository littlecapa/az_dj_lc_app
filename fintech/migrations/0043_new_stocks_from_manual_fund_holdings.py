"""
Migration 0043: Neue Assets für bisher "manuell erfasst" (ohne Asset-Match)
angezeigte ManualFondHolding-Positionen — als Watchlist-Eintrag angelegt
("Fonds-Ergänzungen"), analog zu einem normalen Watchlist-Import, statt als
Dummy-Holdings.

ISINs recherchiert (onvista-Suche); bei CoreWeave zusätzlich gegen die aus
ARK Invests CSV bekannte CUSIP (21873S108, ISO-6166-Prüfziffer berechnet)
gegenverifiziert — beide Quellen stimmen exakt überein (US21873S1087).

Bei mehrfach gelisteten Firmen wurde bewusst gewählt:
- Auto1: deutsche Heimatbörse (DE000A2LQ884), NICHT das US-ADR — passend
  zu allen anderen deutschen Positionen in diesem Bestand.
- Alibaba, Sea, Grupo Cibest, CoreWeave: US-Notierung/ADR (US...), da keine
  deutsche Heimatbörse existiert bzw. die US-ADR die für europäische
  Privatanleger übliche Notierung ist.

get_or_create über die ISIN — bereits existierende Assets werden NICHT
dupliziert. Kein Kurs-Abruf hier (keine Netzwerkzugriffe in einer
Migration) — current_price/price_at_add befüllt sich beim nächsten
normalen update_prices-Lauf.
"""
from django.db import migrations

WATCHLIST_NAME = "Fonds-Ergänzungen"

NEW_STOCKS = [
    ("NL0009805522", "Nebius Group N.V."),
    ("US68389X1054", "Oracle Corp."),
    ("US6391931010", "Navan Inc."),
    ("US01609W1027", "Alibaba Group Holding (ADR)"),
    ("DE000A2LQ884", "Auto1 Group SE"),
    ("KYG254571055", "Credo Technology Group Holding"),
    ("US21873S1087", "CoreWeave Inc."),
    ("SE0003917798", "Sivers Semiconductors AB"),
    ("US0937121079", "Bloom Energy Corp."),
    ("US6877931096", "Oscar Health Inc."),
    ("US4333131039", "Hinge Health Inc."),
    ("US81141R1005", "Sea Ltd (ADR)"),
    ("US40090E1064", "Grupo Cibest S.A. (ADR)"),
]


def add_assets_and_watchlist(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    Watchlist = apps.get_model('fintech', 'Watchlist')
    WatchlistEntry = apps.get_model('fintech', 'WatchlistEntry')
    User = apps.get_model('auth', 'User')

    user = User.objects.filter(is_superuser=True).order_by('id').first()

    watchlist = None
    if user is not None:
        watchlist, _ = Watchlist.objects.get_or_create(name=WATCHLIST_NAME, user=user)

    for isin, name in NEW_STOCKS:
        asset, _ = Asset.objects.get_or_create(
            isin=isin,
            defaults={'name': name, 'asset_class': 'STOCK'},
        )
        if watchlist is not None:
            WatchlistEntry.objects.get_or_create(watchlist=watchlist, asset=asset)


def remove_assets_and_watchlist(apps, schema_editor):
    Watchlist = apps.get_model('fintech', 'Watchlist')
    # Nur die Watchlist entfernen — die Assets selbst NICHT löschen (könnten
    # inzwischen echte Holdings, weitere FondHolding-Mappings o.ä. haben).
    Watchlist.objects.filter(name=WATCHLIST_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0042_tsmc_alias'),
    ]

    operations = [
        migrations.RunPython(add_assets_and_watchlist, remove_assets_and_watchlist),
    ]
