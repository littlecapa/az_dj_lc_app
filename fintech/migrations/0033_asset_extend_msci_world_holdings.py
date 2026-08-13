"""
Migration 0033: Asset.extend_msci_world_holdings

Flag für update_etf_holdings: zusätzlich zu den JustETF-Top-10 die
MSCI-World-Positionen 11-50 von companiesmarketcap.com nachtragen (nur für
bereits direkt gehaltene Aktien).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0032_asset_extend_dax_holdings'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='extend_msci_world_holdings',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Für update_etf_holdings: zusätzlich zu den JustETF-Top-10 die "
                    "MSCI-World-Positionen 11-50 von companiesmarketcap.com nachtragen — nur für "
                    "Aktien, die bereits direkt gehalten werden (Namensabgleich, die Quelle führt "
                    "keine ISIN). Nur bei echten MSCI-World-Trackern aktivieren."
                ),
            ),
        ),
    ]
