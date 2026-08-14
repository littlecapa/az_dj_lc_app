"""
Migration 0037: Asset.extend_etf help_text

Reine Metadaten-Änderung (kein DB-Schema-Effekt): help_text aktualisiert,
da der Namensabgleich seit update_etf_holdings jetzt auch gegen Aktien
läuft, die nur über einen anderen Fonds bekannt sind (Dummy-Holdings),
nicht mehr nur gegen direkt gehaltene.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0036_extend_etf_verbose_name'),
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
                    "companiesmarketcap.com) — nur für Aktien, die im System bereits bekannt "
                    "sind (direkt gehalten oder bereits über einen anderen Fonds erfasst; "
                    "Namensabgleich, diese Quellen führen keine ISIN). Nur bei einem echten "
                    "Tracker des jeweiligen Index setzen. Nur bei asset_class=ETF erlaubt."
                ),
            ),
        ),
    ]
