import django.db.models.deletion
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0047_asset_suspicious_price"),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceAlarm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_price", models.DecimalField(
                    decimal_places=4, max_digits=12,
                    validators=[MinValueValidator(Decimal('0.0001'))],
                    help_text="Kurswert, bei dessen Über- oder Unterschreiten der Alarm auslöst.",
                )),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("asset", models.ForeignKey(
                    to='fintech.asset', on_delete=django.db.models.deletion.CASCADE,
                    related_name='price_alarms',
                )),
            ],
            options={
                "verbose_name": "Preis-Alarm",
                "verbose_name_plural": "Preis-Alarme",
                "ordering": ["asset__name", "target_price"],
            },
        ),
        migrations.CreateModel(
            name="PriceAlarmEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_price", models.DecimalField(decimal_places=4, max_digits=12)),
                ("direction", models.CharField(choices=[('up', 'Aufwärts gekreuzt'), ('down', 'Abwärts gekreuzt')], max_length=4)),
                ("previous_price", models.DecimalField(decimal_places=4, max_digits=12)),
                ("triggered_price", models.DecimalField(decimal_places=4, max_digits=12)),
                ("triggered_at", models.DateTimeField(auto_now_add=True)),
                ("alarm", models.ForeignKey(
                    to='fintech.pricealarm', on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True, related_name='events',
                )),
                ("asset", models.ForeignKey(
                    to='fintech.asset', on_delete=django.db.models.deletion.CASCADE,
                    related_name='price_alarm_events',
                )),
            ],
            options={
                "verbose_name": "Preis-Alarm-Ereignis",
                "verbose_name_plural": "Preis-Alarm-Ereignisse",
                "ordering": ["-triggered_at"],
            },
        ),
    ]
