"""
Migration 0032: Asset.extend_dax_holdings

Flag für update_etf_holdings: zusätzlich zu den JustETF-Top-10 die
DAX-Positionen 11-40 von Wikipedia nachtragen (nur für bereits direkt
gehaltene Aktien).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0031_asset_holdings_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='extend_dax_holdings',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Für update_etf_holdings: zusätzlich zu den JustETF-Top-10 die DAX-Positionen "
                    "11-40 von Wikipedia (de.wikipedia.org/wiki/DAX) nachtragen — nur für Aktien, "
                    "die bereits direkt gehalten werden (Namensabgleich, Wikipedia führt keine "
                    "ISIN). Nur bei echten DAX-Trackern aktivieren."
                ),
            ),
        ),
    ]
