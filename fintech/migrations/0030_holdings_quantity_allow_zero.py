"""
Migration 0030: Holdings.quantity erlaubt jetzt 0.

0 ist ein gültiger, dauerhafter Zustand für einen Dummy-Eintrag (Aktie wird
nur über einen Fonds gehalten, siehe FondHolding), nicht mehr nur ein
Übergangszustand vor dem Löschen.
"""
from decimal import Decimal
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0029_asset_category_fondholding'),
    ]

    operations = [
        migrations.AlterField(
            model_name='holdings',
            name='quantity',
            field=models.DecimalField(
                decimal_places=6,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                help_text=(
                    "Anzahl gehaltener Anteile (auch Bruchteile möglich). "
                    "0 = Dummy-Eintrag für eine Aktie, die nur über einen Fonds "
                    "(FondHolding-Mapping) gehalten wird, nicht direkt."
                ),
            ),
        ),
    ]
