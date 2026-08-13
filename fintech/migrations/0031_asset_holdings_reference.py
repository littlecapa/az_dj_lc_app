"""
Migration 0031: Asset.holdings_reference

Optionale Selbst-Referenz: für update_etf_holdings stattdessen die JustETF-
Holdings-Seite eines anderen (Referenz-)Fonds verwenden — z.B. wenn mehrere
gehaltene ETFs denselben Index abbilden und man nicht jede Anbieter-Seite
einzeln scrapen will.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0030_holdings_quantity_allow_zero'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='holdings_reference',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='holdings_reference_for',
                to='fintech.asset',
                help_text=(
                    "Für update_etf_holdings (Aktien-Look-Through) stattdessen die JustETF-Seite "
                    "DIESES Fonds für die Holdings-Daten verwenden — z.B. 'iShares Core MSCI World' "
                    "(IE00B4L5Y983) als gemeinsame Referenz für andere Anbieter, die denselben Index "
                    "('MSCI World') abbilden. Nur für Fonds mit WIRKLICH identischem Index sinnvoll — "
                    "z.B. NICHT für einen MSCI-ACWI-Fonds, der zusätzlich Emerging Markets enthält. "
                    "Leer = eigene JustETF-Seite verwenden."
                ),
            ),
        ),
    ]
