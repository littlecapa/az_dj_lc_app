"""
Migration 0036: Asset.extend_etf verbose_name

Reine Metadaten-Änderung (kein DB-Schema-Effekt): Admin-Feldbeschriftung
"Extend etf" (Django-Standard-Humanisierung) -> "Extend ETF".
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0035_reset_price_fetch_blocked'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asset',
            name='extend_etf',
            field=models.CharField(
                max_length=20,
                blank=True,
                default='',
                verbose_name="Extend ETF",
                choices=[
                    ('DAX', 'DAX (Wikipedia)'),
                    ('MSCI_WORLD', 'MSCI World (companiesmarketcap.com)'),
                ],
                help_text=(
                    "Für update_etf_holdings: zusätzlich zu den JustETF-Top-10 die Positionen "
                    "11+ von einer externen Quelle nachtragen (DAX: Wikipedia, MSCI World: "
                    "companiesmarketcap.com) — nur für Aktien, die bereits direkt gehalten "
                    "werden (Namensabgleich, diese Quellen führen keine ISIN). Nur bei einem "
                    "echten Tracker des jeweiligen Index setzen. Nur bei asset_class=ETF erlaubt."
                ),
            ),
        ),
    ]
