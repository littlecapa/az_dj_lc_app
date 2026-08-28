from django.db import migrations

# Die 14 Assets aus FIN-442 ("Kurs-Abruf fehlgeschlagen"), automatisch
# price_fetch_blocked=True gesetzt am 25.08.2026. Ursache war für die meisten
# eine fehlende Währung in CurrencyClass (KRW/CNY/TWD) — siehe Migrationen
# 0052-0054. Jetzt entsperren, damit update_prices sie wieder versucht.
ISINS = [
    "GB00B1XZS820",  # Anglo American plc — auch yahoo_symbol=AAL.L (Migration 0054)
    "CNE000000T18",  # China Northern Rare Earth
    "KR7034020008",  # Doosan Enerbility
    "CNE1000009Y1",  # Jinduicheng Molybdenum
    "KR7105560007",  # KB Financial Group
    "KR7047810007",  # Korea Aerospace Industries
    "TW0007610B14",  # Lianyou Metals — braucht TWD/Alpha-Vantage-Fallback (Migration 0052)
    "KR7028260008",  # Samsung C&T
    "KR7009150004",  # Samsung Electro-Mechanics
    "KR7005931001",  # Samsung Electronics
    "KR7055550008",  # Shinhan Financial Group
    "KR7000660001",  # SK hynix
    "KR7402340004",  # SK Square
    "CNE000001D15",  # Xiamen Tungsten
]


def unblock(apps, schema_editor):
    Asset = apps.get_model("fintech", "Asset")
    for isin in ISINS:
        updated = Asset.objects.filter(isin=isin).update(
            price_fetch_blocked=False, price_fetch_failing_since=None,
        )
        if updated:
            print(f"[fin-442-unblock] {isin} entsperrt.")
        else:
            print(f"[fin-442-unblock] Asset {isin} nicht gefunden — übersprungen.")


def reblock(apps, schema_editor):
    """Reverse: wieder sperren (Ausgangszustand vor dieser Migration)."""
    Asset = apps.get_model("fintech", "Asset")
    Asset.objects.filter(isin__in=ISINS).update(price_fetch_blocked=True)


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0054_anglo_american_yahoo_symbol"),
    ]

    operations = [
        migrations.RunPython(unblock, reblock),
    ]
