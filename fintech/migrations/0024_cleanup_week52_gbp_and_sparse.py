"""
Datenmigration: Bereinigt fehlerhafte FiftyTwoWeekRange-Einträge.

Hintergrund
-----------
Migration 0023 lief mit einer älteren Version, die nur Einträge mit
current > high * 1.2 gelöscht hat. Zwei weitere Fehlerquellen wurden
seitdem identifiziert:

1. GBp-Normalisierung:
   Yahoo gibt UK-Aktien (GB*) in GBp (Pence) zurück. Einträge mit
   yahoo_currency='GBp' haben Werte 100x zu groß gespeichert.
   → Alle Werte durch 100 teilen, Währung auf 'GBP' setzen.

2. Spärlich gehandelte Sekundärlisting (z.B. Stuttgart .SG für NO/DK):
   Wenn Yahoo ein Stuttgarter Listing (EUR) statt der Primärbörse (NOK/DKK)
   findet, kann das 52W-Tief extrem niedrig sein (z.B. 3 EUR statt 33 EUR).
   Erkennbar: high/low > 8 (unrealistisch große Jahresspanne).
   → Eintrag löschen; wird mit korrekter Primärbörse neu geladen.

3. Umgekehrter Extremwert: high > current * 5
   Eintrag löschen.
"""

from django.db import migrations


def cleanup_week52(apps, schema_editor):
    FiftyTwoWeekRange = apps.get_model('fintech', 'FiftyTwoWeekRange')

    # 1. GBp → GBP normalisieren
    gbp_fixed = 0
    for r in FiftyTwoWeekRange.objects.filter(yahoo_currency='GBp'):
        try:
            r.week52_high         = r.week52_high / 100
            r.week52_low          = r.week52_low  / 100
            if r.yahoo_current_price is not None:
                r.yahoo_current_price = r.yahoo_current_price / 100
            r.yahoo_currency = 'GBP'
            r.save()
            gbp_fixed += 1
            print(f"  GBp→GBP: asset_id={r.asset_id} H={r.week52_high} L={r.week52_low}")
        except Exception as exc:
            print(f"  GBp→GBP failed for asset_id={r.asset_id}: {exc}")
    print(f"GBp→GBP: {gbp_fixed} entries fixed")

    # 2. Ungültige Einträge löschen
    deleted = 0
    for r in FiftyTwoWeekRange.objects.all():
        try:
            high = float(r.week52_high)
            low  = float(r.week52_low)
            cur  = float(r.yahoo_current_price) if r.yahoo_current_price else None
            reason = None

            if cur is not None and cur > high * 1.20:
                reason = f"current={cur} > high={high}*1.2"
            elif cur is not None and high > cur * 5.0:
                reason = f"high={high} > current={cur}*5"
            elif low > 0 and high / low > 8.0:
                reason = f"high/low={high/low:.1f} > 8 (sparse listing)"

            if reason:
                print(f"  Delete: asset_id={r.asset_id} ({reason})")
                r.delete()
                deleted += 1
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    print(f"Invalid: {deleted} entries deleted")


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0023_cleanup_invalid_week52_data'),
    ]

    operations = [
        migrations.RunPython(cleanup_week52, migrations.RunPython.noop),
    ]
