"""
Migration 0042: TSMC-Alias

companiesmarketcap.com/Factsheets schreiben Taiwan Semiconductor teils als
Kürzel "TSMC" (z.B. bei MSCI-World-Top-50). search_term ist bewusst nur
"Taiwan" (nicht "Taiwan Semiconductor") — Broker-Exporte kürzen
"Semiconductor" oft zu "Semiconduct." ab (siehe Factsheet-Beispiel "Taiwan
Semiconduct.Manufact.Co"), ein volles "Semiconductor" würde daran
vorbeigehen. "Taiwan" allein ist stabil genug, um TSMC eindeutig zu treffen.
"""
from django.db import migrations


def add_alias(apps, schema_editor):
    NameAlias = apps.get_model('fintech', 'NameAlias')
    NameAlias.objects.update_or_create(
        external_name='TSMC',
        defaults={'search_term': 'Taiwan'},
    )


def remove_alias(apps, schema_editor):
    NameAlias = apps.get_model('fintech', 'NameAlias')
    NameAlias.objects.filter(external_name='TSMC').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0041_name_alias'),
    ]

    operations = [
        migrations.RunPython(add_alias, remove_alias),
    ]
