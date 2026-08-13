"""
Migration 0029: FondHolding.

Manuelles Mapping Fonds-ISIN -> Holding-ISIN -> Prozent, Basis für die
Aktien-Look-Through-Übersicht (/fintech/overall-stocks/).
"""
from decimal import Decimal
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0028_asset_price_fetch_blocked'),
    ]

    operations = [
        migrations.CreateModel(
            name='FondHolding',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('percentage', models.DecimalField(
                    decimal_places=3, max_digits=6,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0')),
                        django.core.validators.MaxValueValidator(Decimal('100')),
                    ],
                    help_text='Gewichtung der Aktie im Fonds in Prozent, z.B. 4.250 für 4,25%',
                )),
                ('fund', models.ForeignKey(
                    to='fintech.asset', on_delete=django.db.models.deletion.CASCADE,
                    related_name='fund_holdings',
                    help_text='Der Fonds/ETF (muss als Asset existieren, i.d.R. eine deiner Holdings)',
                )),
                ('holding', models.ForeignKey(
                    to='fintech.asset', on_delete=django.db.models.deletion.CASCADE,
                    related_name='held_by_funds',
                    help_text='Die Einzelaktie, die der Fonds hält (muss als Asset existieren)',
                )),
            ],
            options={
                'verbose_name': 'Fonds-Holding',
                'verbose_name_plural': 'Fonds-Holdings',
                'ordering': ['fund__name', '-percentage'],
                'unique_together': {('fund', 'holding')},
            },
        ),
    ]
