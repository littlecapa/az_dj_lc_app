"""
Migration 0040: Manuelle Top-10-Holdings für EM Digital Leaders R und
The Digital Leaders Fund - Anteilklasse R (beide ohne Holdings-Daten bei
JustETF), aus deren Factsheets übernommen.

Bei "The Digital Leaders Fund" wurde die Position "EM Digital Leaders
Inhaber-Anteilsklasse I" (2,95 %) bewusst ausgelassen — das ist selbst ein
Fondsanteil (Fund-of-Funds-Position), keine Einzelaktie, und gehört nicht
in den Aktien-Look-Through.
"""
from decimal import Decimal
from django.db import migrations

EM_DIGITAL_LEADERS_ISIN = 'DE000A2QK5J1'
EM_DIGITAL_LEADERS_HOLDINGS = [
    ("Samsung Electronics", Decimal('8.600')),
    ("Taiwan Semiconductor", Decimal('7.400')),
    ("SK Hynix", Decimal('5.800')),
    ("SK Square", Decimal('4.800')),
    ("Alibaba Group", Decimal('4.600')),
    ("Nebius Group", Decimal('3.500')),
    ("Sea", Decimal('3.500')),
    ("Nu Holdings", Decimal('3.400')),
    ("PC Partner Group", Decimal('3.400')),
    ("Grupo Cibest", Decimal('3.300')),
]

DIGITAL_LEADERS_FUND_ISIN = 'DE000A2H7N24'
DIGITAL_LEADERS_FUND_HOLDINGS = [
    ("Nebius Group", Decimal('5.200')),
    ("Samsung Electronics", Decimal('5.030')),
    ("Oracle", Decimal('4.990')),
    ("Credo Technology Group", Decimal('3.640')),
    ("CoreWeave", Decimal('3.510')),
    ("Sivers Semiconductors", Decimal('3.380')),
    ("Bloom Energy", Decimal('3.340')),
    ("NVIDIA", Decimal('2.920')),
    ("Datadog", Decimal('2.870')),
]

FUNDS = [
    (EM_DIGITAL_LEADERS_ISIN, EM_DIGITAL_LEADERS_HOLDINGS),
    (DIGITAL_LEADERS_FUND_ISIN, DIGITAL_LEADERS_FUND_HOLDINGS),
]


def add_manual_holdings(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    ManualFondHolding = apps.get_model('fintech', 'ManualFondHolding')
    for fund_isin, holdings in FUNDS:
        try:
            fund = Asset.objects.get(isin=fund_isin)
        except Asset.DoesNotExist:
            continue
        for name, percentage in holdings:
            ManualFondHolding.objects.update_or_create(
                fund=fund, holding_name=name,
                defaults={'percentage': percentage},
            )


def remove_manual_holdings(apps, schema_editor):
    ManualFondHolding = apps.get_model('fintech', 'ManualFondHolding')
    for fund_isin, holdings in FUNDS:
        ManualFondHolding.objects.filter(
            fund_id=fund_isin,
            holding_name__in=[name for name, _ in holdings],
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0039_extend_etf_help_text_v2'),
    ]

    operations = [
        migrations.RunPython(add_manual_holdings, remove_manual_holdings),
    ]
