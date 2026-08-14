"""
Migration 0039: Asset.extend_etf help_text (v2)

Reine Metadaten-Änderung (kein DB-Schema-Effekt): help_text aktualisiert,
da update_etf_holdings die DAX-/MSCI-World-Tail-Erweiterung nicht mehr per
festem Positions-Cutoff (z.B. "ab Position 11") macht, sondern pro Aktie
prüft, ob für den Fonds schon ein JustETF-Mapping existiert (Bugfix:
Rheinmetall lag in Wikipedias DAX-Top-10, aber nicht in JustETFs Top-10 für
den DAX-ETF, und fiel bei einem festen Cutoff komplett durch).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0038_ark_ticker_manual_fond_holding'),
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
                    "Für update_etf_holdings: zusätzlich zu den JustETF-Top-10 die übrigen "
                    "Positionen (noch kein Mapping für diesen Fonds) von einer externen Quelle "
                    "nachtragen (DAX: Wikipedia, MSCI World: companiesmarketcap.com) — nur für "
                    "Aktien, die im System bereits bekannt sind (direkt gehalten oder bereits "
                    "über einen anderen Fonds erfasst; Namensabgleich, diese Quellen führen "
                    "keine ISIN). Nur bei einem echten Tracker des jeweiligen Index setzen. Nur "
                    "bei asset_class=ETF erlaubt."
                ),
            ),
        ),
    ]
