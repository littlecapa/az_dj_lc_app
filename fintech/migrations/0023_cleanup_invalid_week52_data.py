"""
Datenmigration: Zwei Bereinigungen für FiftyTwoWeekRange-Einträge:

1. GBp → GBP-Normalisierung:
   Yahoo gibt UK-Kurse in Pence (GBp) zurück. Bestehende Einträge mit
   yahoo_currency='GBp' haben Werte x100 zu groß gespeichert.
   → Alle Werte durch 100 teilen, Währung auf 'GBP' setzen.

2. Ungültige Einträge löschen (current > high * 1.2):
   Für dünn gehandelte Nebenbörsenlisting (.SG) liefert Yahoo manchmal
   veraltete 52W-Daten, bei denen der aktuelle Kurs weit über dem
   angeblichen 52W-Hoch liegt. Diese Einträge werden gelöscht und beim
   nächsten /fintech/overall/-Aufruf neu ermittelt.
"""

from django.db import migrations


def cleanup_gbp_and_invalid(apps, schema_editor):
    FiftyTwoWeekRange = apps.get_model('fintech', 'FiftyTwoWeekRange')

    # 1. GBp → GBP normalisieren
    gbp_fixed = 0
    for r in FiftyTwoWeekRange.objects.filter(yahoo_currency='GBp'):
        try:
            r.week52_high         = r.week52_high         / 100
            r.week52_low          = r.week52_low          / 100
            if r.yahoo_current_price is not None:
                r.yahoo_current_price = r.yahoo_current_price / 100
            r.yahoo_currency = 'GBP'
            r.save()
            gbp_fixed += 1
            print(f"  GBp→GBP fixed: asset_id={r.asset_id} "
                  f"H={r.week52_high} L={r.week52_low} cur={r.yahoo_current_price}")
        except Exception as exc:
            print(f"  GBp→GBP failed for asset_id={r.asset_id}: {exc}")

    print(f"GBp→GBP: fixed {gbp_fixed} entries")

    # 2. Ungültige Einträge löschen:
    #    a) current > high * 1.2  → Kurs über 52W-Hoch (unmöglich)
    #    b) high > current * 5    → 52W-Hoch >5x aktueller Kurs (Artefakt/Split)
    deleted = 0
    for r in FiftyTwoWeekRange.objects.exclude(yahoo_current_price__isnull=True):
        try:
            cur  = float(r.yahoo_current_price)
            high = float(r.week52_high)
            reason = None
            if cur > high * 1.20:
                reason = f"cur={cur} > high={high}*1.2"
            elif high > cur * 5.0:
                reason = f"high={high} > cur={cur}*5"
            if reason:
                print(f"  Deleted invalid 52W: asset_id={r.asset_id} ({reason})")
                r.delete()
                deleted += 1
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    print(f"Invalid 52W: deleted {deleted} entries")


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0022_alter_fiftytwoweekrange_week52_high_and_more'),
    ]

    operations = [
        migrations.RunPython(cleanup_gbp_and_invalid, migrations.RunPython.noop),
    ]
