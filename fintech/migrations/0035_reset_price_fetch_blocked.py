"""
Migration 0035: price_fetch_blocked bei allen Assets zurücksetzen

Setzt Asset.price_fetch_blocked für alle bestehenden Assets auf False.
"""
from django.db import migrations


def reset_price_fetch_blocked_forward(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    Asset.objects.update(price_fetch_blocked=False)


def reset_price_fetch_blocked_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0034_asset_extend_etf'),
    ]

    operations = [
        migrations.RunPython(reset_price_fetch_blocked_forward, reset_price_fetch_blocked_backward),
    ]
