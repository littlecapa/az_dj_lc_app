from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0009_holdings_stake_recovered'),
    ]

    operations = [
        # price_at_add nullable machen (Auto-Fill via save())
        migrations.AlterField(
            model_name='watchlistentry',
            name='price_at_add',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Kurs zum Zeitpunkt der Aufnahme (wird automatisch befüllt)',
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.0001'))],
            ),
        ),
        # notes erweitern
        migrations.AlterField(
            model_name='watchlistentry',
            name='notes',
            field=models.CharField(
                blank=True,
                help_text='Grund für Watchlist-Aufnahme',
                max_length=500,
            ),
        ),
        # source neu
        migrations.AddField(
            model_name='watchlistentry',
            name='source',
            field=models.CharField(
                blank=True,
                help_text='Quelle des Eintrags (z. B. URL, Analyst, Nachricht)',
                max_length=300,
            ),
        ),
    ]
