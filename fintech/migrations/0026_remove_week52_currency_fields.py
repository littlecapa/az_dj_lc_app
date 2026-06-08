"""
Migration 0026: Entfernt yahoo_currency und yahoo_current_price aus FiftyTwoWeekRange.

Alle 52W-Werte werden ab jetzt in EUR gespeichert. Bestehende Einträge können
nicht sicher konvertiert werden (Währung unbekannt nach Felddeletion), daher
werden alle bestehenden Einträge gelöscht — sie werden beim nächsten
Overall-Seitenaufruf korrekt in EUR neu befüllt.
"""
from django.db import migrations, models


def delete_all_week52_entries(apps, schema_editor):
    FiftyTwoWeekRange = apps.get_model('fintech', 'FiftyTwoWeekRange')
    count = FiftyTwoWeekRange.objects.count()
    FiftyTwoWeekRange.objects.all().delete()
    print(f"\n0026: {count} FiftyTwoWeekRange-Einträge gelöscht (werden in EUR neu befüllt).")


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0025_cleanup_yahoo_symbols_in_asset'),
    ]

    operations = [
        migrations.RunPython(delete_all_week52_entries, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='fiftytwoweekrange',
            name='yahoo_currency',
        ),
        migrations.RemoveField(
            model_name='fiftytwoweekrange',
            name='yahoo_current_price',
        ),
        migrations.AlterField(
            model_name='fiftytwoweekrange',
            name='week52_high',
            field=models.DecimalField(decimal_places=4, help_text='52-Wochen-Hoch in EUR', max_digits=12),
        ),
        migrations.AlterField(
            model_name='fiftytwoweekrange',
            name='week52_low',
            field=models.DecimalField(decimal_places=4, help_text='52-Wochen-Tief in EUR', max_digits=12),
        ),
    ]
