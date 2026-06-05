"""
Data migration: weist allen Holdings die neuen Kategorien zu.
Mapping basiert auf ISIN → neue Kategorie (aus portfolio_categories.csv).
Alte Kategorie-Werte (1–14, 99) bleiben im Model erhalten bis alle
Holdings migriert und die Legacy-Werte entfernt werden können.
"""
from django.db import migrations

# ISIN → neue Kategorie-ID
ISIN_CATEGORY_MAP = {
    # Insurance (20)
    'DE0008430026': 20,  # Münchener Rück
    'DE0008402215': 20,  # Hannover Rück
    'DE000TLX1005': 20,  # Talanx
    'DE0008404005': 20,  # Allianz

    # Finance Global (21)
    'US0846707026': 21,  # Berkshire Hathaway B
    'US6174464486': 21,  # Morgan Stanley
    'US0640581007': 21,  # Bank of New York Mellon
    'US09290D1019': 21,  # BlackRock
    'US78409V1044': 21,  # S&P Global
    'US55354G1004': 21,  # MSCI Inc

    # EU Technology (22)
    'DE0007164600': 22,  # SAP
    'DE0006580806': 22,  # Mensch & Maschine
    'DE0007236101': 22,  # Siemens
    'NL0010273215': 22,  # ASML

    # US Big Tech (23)
    'US0378331005': 23,  # Apple
    'US5949181045': 23,  # Microsoft
    'US02079K3059': 23,  # Alphabet A
    'US0231351067': 23,  # Amazon
    'US64110L1061': 23,  # Netflix
    'US90353T1007': 23,  # Uber Technologies

    # Cybersecurity & Cloud (24)
    'US22788C1053': 24,  # Crowdstrike
    'US23804L1035': 24,  # Datadog
    'IE00BLPK3577': 24,  # WisdomTree Cybersecurity ETF
    'DE000VJ6AJZ8': 24,  # Aktienanleihe Salesforce

    # Defense (25)
    'DE0007030009': 25,  # Rheinmetall
    'NL0000235190': 25,  # Airbus
    'US0080731088': 25,  # AeroVironment
    'AU000000DRO2': 25,  # DroneShield
    'IE0008GRJRO8': 25,  # SPDR Europe Defense ETF
    'IE0002Y8CX98': 25,  # WisdomTree Europe Defence ETF

    # Energy (26)
    'NO0010096985': 26,  # Equinor
    'FR0000120271': 26,  # TotalEnergies
    'IE00B42NKQ00': 26,  # iShares S&P 500 Energy ETF
    'DE000ENAG999': 26,  # E.ON
    'DE0007037129': 26,  # RWE
    'ES0144580Y14': 26,  # Iberdrola
    'US36828A1016': 26,  # GE Vernova
    'US92840M1027': 26,  # Vistra
    'IE000M7V94E1': 26,  # VanEck Uranium & Nuclear ETF

    # AI & Robotics (27)
    'US7010941042': 27,  # Parker-Hannifin
    'IE00BYZK4552': 27,  # iShares Automation & Robotics ETF
    'IE00BLCHJB90': 27,  # Global X Robotics & AI ETF
    'IE000GA3D489': 27,  # ARK Innovation ETF
    'DE000A2QK5J1': 27,  # EM Digital Leaders
    'DE000A2H7N24': 27,  # Digital Leaders Fund
    'DE000A2N8127': 27,  # BIT Global Technology Leaders
    'IE00BHZRR030': 27,  # Franklin FTSE Korea ETF
    'JP3435000009': 27,  # Sony Group

    # Pharma & Biotech (28)
    'GB0009895292': 28,  # AstraZeneca
    'DK0062498333': 28,  # Novo-Nordisk
    'US09075V1026': 28,  # BioNTech ADR
    'DE0005664809': 28,  # Evotec

    # Cars (29)
    'DE0005190003': 29,  # BMW
    'DE0007100000': 29,  # Mercedes-Benz
    'DE000PAG9113': 29,  # Porsche Vz

    # Consumer & Brands (30)
    'IE00BYTBXV33': 30,  # Ryanair
    'CH1134540470': 30,  # On Holding
    'GB00BVZK7T90': 30,  # Unilever
    'FR0000120644': 30,  # Danone
    'US9311421039': 30,  # Walmart
    'US88579Y1010': 30,  # 3M

    # Infrastructure (31)
    'IE000NXF88S1': 31,  # VanEck Oil Services ETF
    'DE000A255F11': 31,  # Friedrich Vorwerk
    'DE000WACK012': 31,  # Wacker Neuson
    'DK0010287663': 31,  # NKT
    'DE000A0H08F7': 31,  # iShares STOXX Europe 600 Construction & Materials ETF
    'IE000LTA2082': 31,  # Amundi S&P Global Industrials ETF

    # Mining & Resources (32)
    'GB0007188757': 32,  # Rio Tinto
    'US35671D8570': 32,  # Freeport-McMoran
    'US5533681012': 32,  # MP Materials
    'IE00063FT9K6': 32,  # iShares Copper Miners ETF
    'IE0002PG6CA6': 32,  # VanEck Rare Earth ETF

    # Precious Metals & Bonds (33)
    'DE000A2T5DZ1': 33,  # Xtrackers Physical Gold ETC
    'DE000A1E0HS6': 33,  # Xtrackers Physical Silver ETC
    'LU1109942653': 33,  # Xtrackers EUR High Yield Corp Bond ETF

    # Crypto & Blockchain (34)
    'US19260Q1076': 34,  # Coinbase
    'XS2940466316': 34,  # iShares Bitcoin ETP
    'AU0000185993': 34,  # IREN

    # Core Investment (35)
    'DE0005557508': 35,  # Deutsche Telekom
    'DE0005552004': 35,  # Deutsche Post
    'DE0005933931': 35,  # iShares Core DAX ETF
    'DE0009757740': 35,  # UniEuroAktien
    'IE000MWUQBJ0': 35,  # HSBC Euro Stoxx 50 ETF
    'LU0322248146': 35,  # Xtrackers SLI ETF
    'LU1829219390': 35,  # Amundi Euro Stoxx Banks ETF
    'NL0011683594': 35,  # VanEck Masters DM Div ETF
    'LU2439874319': 35,  # Frankfurter Modern Value ETF
    'LU0274208692': 35,  # Xtrackers MSCI World ETF

    # Asia & Emerging Markets (36)
    'IE00BMWXKN31': 36,  # HSBC Hang Seng TECH ETF
    'IE00094FRAA6': 36,  # Global X China EV ETF

    # Chemicals (37)
    'DE000A2G8ZX8': 37,  # Pyrum Innovations
    'DE000BASF111': 37,  # BASF
    'DE000EVNK013': 37,  # Evonik
}


def migrate_categories(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    Holdings = apps.get_model('fintech', 'Holdings')

    updated = 0
    skipped = []

    for isin, new_category in ISIN_CATEGORY_MAP.items():
        try:
            asset = Asset.objects.get(isin=isin)
        except Asset.DoesNotExist:
            skipped.append(isin)
            continue
        count = Holdings.objects.filter(asset=asset).update(category=new_category)
        updated += count

    if skipped:
        print(f"\n  Warnung: {len(skipped)} ISINs nicht in DB gefunden: {skipped}")
    print(f"\n  {updated} Holdings auf neue Kategorien migriert.")


def reverse_migration(apps, schema_editor):
    # Kein Rollback — alte Werte sind nicht mehr bekannt
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0012_alter_watchlistentry_options'),
    ]

    operations = [
        migrations.RunPython(migrate_categories, reverse_migration),
    ]
