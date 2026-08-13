"""
Migration 0034: extend_dax_holdings + extend_msci_world_holdings -> extend_etf

Vereinheitlicht die beiden Boolean-Flags zu einem einzigen Auswahlfeld
(DAX / MSCI_WORLD / leer). Bestehende True-Werte werden übernommen, bevor
die alten Felder entfernt werden.
"""
from django.db import migrations, models


def migrate_extend_flags_forward(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    Asset.objects.filter(extend_dax_holdings=True).update(extend_etf='DAX')
    Asset.objects.filter(extend_msci_world_holdings=True).update(extend_etf='MSCI_WORLD')


def migrate_extend_flags_backward(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    Asset.objects.filter(extend_etf='DAX').update(extend_dax_holdings=True)
    Asset.objects.filter(extend_etf='MSCI_WORLD').update(extend_msci_world_holdings=True)


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0033_asset_extend_msci_world_holdings'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='extend_etf',
            field=models.CharField(
                max_length=20,
                blank=True,
                default='',
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
        migrations.RunPython(migrate_extend_flags_forward, migrate_extend_flags_backward),
        migrations.RemoveField(
            model_name='asset',
            name='extend_dax_holdings',
        ),
        migrations.RemoveField(
            model_name='asset',
            name='extend_msci_world_holdings',
        ),
    ]
