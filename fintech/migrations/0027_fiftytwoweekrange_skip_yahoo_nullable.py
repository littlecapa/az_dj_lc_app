"""
Migration 0027: Blacklist-Flag und nullable Felder für FiftyTwoWeekRange.

- skip_yahoo: Boolean, True = kein Yahoo-Abruf, Eintrag wird nie gelöscht
- week52_high / week52_low: jetzt nullable (Eintrag kann ohne Werte existieren)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0026_remove_week52_currency_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiftytwoweekrange',
            name='skip_yahoo',
            field=models.BooleanField(
                default=False,
                help_text='True = Yahoo-Abfrage sperren (z.B. ETFs ohne sinnvolle 52W-Daten). Wird bei Refresh nicht gelöscht.',
            ),
        ),
        migrations.AlterField(
            model_name='fiftytwoweekrange',
            name='week52_high',
            field=models.DecimalField(
                decimal_places=4, max_digits=12,
                null=True, blank=True,
                help_text='52-Wochen-Hoch in EUR',
            ),
        ),
        migrations.AlterField(
            model_name='fiftytwoweekrange',
            name='week52_low',
            field=models.DecimalField(
                decimal_places=4, max_digits=12,
                null=True, blank=True,
                help_text='52-Wochen-Tief in EUR',
            ),
        ),
    ]
