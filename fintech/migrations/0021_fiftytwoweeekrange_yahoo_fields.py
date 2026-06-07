from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0020_finconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiftytwoweekrange',
            name='yahoo_currency',
            field=models.CharField(
                blank=True, default='', max_length=10,
                help_text='Währung laut Yahoo (kann von Asset-Währung abweichen, z.B. USD vs EUR)',
            ),
        ),
        migrations.AddField(
            model_name='fiftytwoweekrange',
            name='yahoo_current_price',
            field=models.DecimalField(
                blank=True, null=True, max_digits=12, decimal_places=4,
                help_text='Aktueller Kurs laut Yahoo (gleiche Währung wie 52W-Werte, für Prozentberechnung)',
            ),
        ),
    ]
