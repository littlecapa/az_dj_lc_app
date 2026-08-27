from decimal import Decimal

from django.db import migrations

# Bestände, für die am 2026-08-27 auf Wunsch ein Trailing-Stop-Loss mit dem
# Default-Prozentsatz (10%) aktiviert wird. Referenzhoch startet jeweils beim
# aktuellen Asset.current_price zum Zeitpunkt, an dem diese Migration läuft
# (nicht ein zum Schreibzeitpunkt hartkodierter Kurs).
ISINS = [
    "NL0011683594",  # VanEck Morningstar Developed Markets Dividend Leaders
    "DE0005933931",  # iShares Core DAX
    "DE0008404005",  # Allianz
    "DE000TLX1005",  # Talanx
    "US09290D1019",  # BlackRock
    "DE0005552004",  # Deutsche Post
    "US88579Y1010",  # 3M
    "DE000DTR0CK8",  # Daimler Truck
    "NL0000235190",  # Airbus
    "FR0000120271",  # TotalEnergies
    "US02079K3059",  # Alphabet A
    "US0378331005",  # Apple
    "LU1829219390",  # Amundi Euro Stoxx Banks (Acc)
    "US0640581007",  # Bank of New York Mellon
    "IE00BHZRR030",  # Franklin FTSE Korea (Acc)
    "US7010941042",  # Parker-Hannifin Corp
]

DEFAULT_TRAIL_PERCENT = Decimal("10.00")


def activate_trailing_stops(apps, schema_editor):
    Asset = apps.get_model("fintech", "Asset")
    Holdings = apps.get_model("fintech", "Holdings")
    TrailingStopLoss = apps.get_model("fintech", "TrailingStopLoss")

    for isin in ISINS:
        asset = Asset.objects.filter(isin=isin).first()
        if asset is None:
            print(f"[trailing-stop-migration] Asset {isin} nicht gefunden — übersprungen.")
            continue

        holding = Holdings.objects.filter(asset=asset).first()
        if holding is None:
            print(f"[trailing-stop-migration] Kein Bestand für {isin} ({asset.name}) — übersprungen.")
            continue

        if not asset.current_price:
            print(f"[trailing-stop-migration] Kein aktueller Kurs für {isin} ({asset.name}) — übersprungen.")
            continue

        TrailingStopLoss.objects.update_or_create(
            holdings=holding,
            defaults={
                "trail_percent": DEFAULT_TRAIL_PERCENT,
                "activated_price": asset.current_price,
                "reference_price": asset.current_price,
                "is_active": True,
            },
        )
        print(f"[trailing-stop-migration] Trailing-Stop aktiviert: {isin} ({asset.name}) @ {asset.current_price}")


def deactivate_trailing_stops(apps, schema_editor):
    """Reverse: die von dieser Migration angelegten Trailing-Stops wieder löschen."""
    TrailingStopLoss = apps.get_model("fintech", "TrailingStopLoss")
    TrailingStopLoss.objects.filter(holdings__asset__isin__in=ISINS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0050_trailingstoploss_trailingstopevent"),
    ]

    operations = [
        migrations.RunPython(activate_trailing_stops, deactivate_trailing_stops),
    ]
