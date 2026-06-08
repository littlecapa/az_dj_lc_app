"""
Migration 0025: Normalisiert Asset.symbol auf TradingView-URL-Format.

TradingView-URLs verwenden '-' als Trennzeichen: https://de.tradingview.com/symbols/HKEX-9880/

Symbole können in verschiedenen Formaten vorliegen:
  - OpenFIGI-Format:  "HKEX:9880"  (Doppelpunkt)
  - Yahoo-Format:     "9880.HK"    (Punkt)
  - Bereits korrekt:  "HKEX-9880"  (Bindestrich)

Diese Migration normalisiert alle gespeicherten Symbole:
  ':' → '-'  und  '.' → '-'
"""
from django.db import migrations


def normalize_symbols(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    changed = []
    for asset in Asset.objects.exclude(symbol__isnull=True).exclude(symbol=''):
        sym = asset.symbol or ''
        normalized = sym.replace(':', '-').replace('.', '-')
        if normalized != sym:
            changed.append(f"{asset.isin}: '{sym}' → '{normalized}'")
            asset.symbol = normalized
            asset.save(update_fields=['symbol'])

    if changed:
        print(f"\n0025: {len(changed)} Symbol(e) normalisiert:")
        for line in changed:
            print(f"  {line}")
    else:
        print("\n0025: Alle Symbole bereits im korrekten Format.")


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0024_cleanup_week52_gbp_and_sparse'),
    ]

    operations = [
        migrations.RunPython(normalize_symbols, migrations.RunPython.noop),
    ]
