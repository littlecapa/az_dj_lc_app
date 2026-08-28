from django.db import migrations

ISIN = "GB00B1XZS820"
YAHOO_SYMBOL = "AAL.L"  # verifiziert gegen query1.finance.yahoo.com/v8/finance/chart/AAL.L


def set_yahoo_symbol(apps, schema_editor):
    Asset = apps.get_model("fintech", "Asset")
    updated = Asset.objects.filter(isin=ISIN).update(yahoo_symbol=YAHOO_SYMBOL)
    if updated:
        print(f"[yahoo-symbol-migration] {ISIN} → yahoo_symbol='{YAHOO_SYMBOL}' gesetzt.")
    else:
        print(f"[yahoo-symbol-migration] Asset {ISIN} nicht gefunden — übersprungen.")


def unset_yahoo_symbol(apps, schema_editor):
    Asset = apps.get_model("fintech", "Asset")
    Asset.objects.filter(isin=ISIN, yahoo_symbol=YAHOO_SYMBOL).update(yahoo_symbol=None)


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0053_asset_yahoo_symbol"),
    ]

    operations = [
        migrations.RunPython(set_yahoo_symbol, unset_yahoo_symbol),
    ]
