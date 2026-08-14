"""
Migration 0038: Asset.ark_ticker + neues Model ManualFondHolding

- Asset.ark_ticker: für update_etf_holdings, um statt JustETF-Top-10 die
  vollständige ARK-Invest-CSV-Holdings-Liste zu verwenden (ISIN aus CUSIP
  berechnet, kein Namensabgleich nötig).
- ManualFondHolding: halb-manuell gepflegte Fonds-Holdings (Freitext-Name,
  keine ISIN nötig) für aktiv gemanagte Fonds ohne strukturierte Quelle —
  hat pro Fonds Vorrang vor FondHolding, wenn Einträge vorhanden sind.
- Befüllt direkt die Top-10 für "BIT Global Technology Leaders R - I"
  (DE000A2N8127), manuell aus deren Factsheet übernommen.
"""
import django.db.models.deletion
import django.core.validators
from decimal import Decimal
from django.db import migrations, models

BIT_FUND_ISIN = 'DE000A2N8127'
BIT_HOLDINGS = [
    ("Amazon", Decimal('10.100')),
    ("IREN", Decimal('9.000')),
    ("Micron", Decimal('7.900')),
    ("Robinhood", Decimal('6.700')),
    ("Navan", Decimal('5.000')),
    ("TSMC", Decimal('4.600')),
    ("Auto1", Decimal('4.500')),
    ("Infineon", Decimal('4.100')),
    ("Oscar Health", Decimal('4.000')),
    ("Hinge Health", Decimal('3.800')),
]


def add_bit_manual_holdings(apps, schema_editor):
    Asset = apps.get_model('fintech', 'Asset')
    ManualFondHolding = apps.get_model('fintech', 'ManualFondHolding')
    try:
        fund = Asset.objects.get(isin=BIT_FUND_ISIN)
    except Asset.DoesNotExist:
        return
    for name, percentage in BIT_HOLDINGS:
        ManualFondHolding.objects.update_or_create(
            fund=fund, holding_name=name,
            defaults={'percentage': percentage},
        )


def remove_bit_manual_holdings(apps, schema_editor):
    ManualFondHolding = apps.get_model('fintech', 'ManualFondHolding')
    ManualFondHolding.objects.filter(
        fund_id=BIT_FUND_ISIN,
        holding_name__in=[name for name, _ in BIT_HOLDINGS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0037_extend_etf_help_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='ark_ticker',
            field=models.CharField(
                max_length=10,
                blank=True,
                default='',
                verbose_name="ARK-Ticker",
                help_text=(
                    "Für update_etf_holdings: statt der JustETF-Top-10 die vollständige, "
                    "tagesaktuelle Holdings-Liste direkt von ARK Invest verwenden (z.B. 'ARKK' "
                    "für den ARK Innovation ETF) — liefert CUSIP, woraus die ISIN berechnet "
                    "wird, kein Namensabgleich nötig. Nur sinnvoll für Fonds, die tatsächlich "
                    "einen ARK-ETF 1:1 abbilden/nachbilden (z.B. 'ARK Innovation (Acc)'). Nur "
                    "bei asset_class=ETF erlaubt."
                ),
            ),
        ),
        migrations.CreateModel(
            name='ManualFondHolding',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('holding_name', models.CharField(
                    max_length=200,
                    help_text="Name der Position, z.B. aus einem Factsheet abgetippt (keine ISIN nötig).",
                )),
                ('percentage', models.DecimalField(
                    max_digits=6, decimal_places=3,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0')),
                        django.core.validators.MaxValueValidator(Decimal('100')),
                    ],
                    help_text="Gewichtung in Prozent, z.B. 10.100 für 10,1%",
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('fund', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='manual_fund_holdings',
                    to='fintech.asset',
                    help_text="Der Fonds/ETF (muss als Asset existieren, i.d.R. eine deiner Holdings)",
                )),
            ],
            options={
                'verbose_name': "Manuelles Fonds-Holding",
                'verbose_name_plural': "Manuelle Fonds-Holdings",
                'ordering': ['fund__name', '-percentage'],
            },
        ),
        migrations.RunPython(add_bit_manual_holdings, remove_bit_manual_holdings),
    ]
