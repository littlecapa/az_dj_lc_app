import django.db.models.deletion
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0049_pricealarmevent_notified_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrailingStopLoss",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trail_percent", models.DecimalField(
                    decimal_places=2, max_digits=5, default=Decimal('10.00'),
                    validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('99.99'))],
                    help_text="Prozentualer Abstand zum Referenzhoch, bei dessen Unterschreiten der Alarm auslöst.",
                )),
                ("activated_price", models.DecimalField(
                    decimal_places=4, max_digits=12,
                    help_text="Kurs bei Aktivierung — unveränderlicher Startwert des Referenzhochs.",
                )),
                ("reference_price", models.DecimalField(
                    decimal_places=4, max_digits=12,
                    help_text="Aktuelles Referenzhoch seit Aktivierung. Steigt mit neuen Kurshochs, fällt nie.",
                )),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("holdings", models.OneToOneField(
                    to='fintech.holdings', on_delete=django.db.models.deletion.CASCADE,
                    related_name='trailing_stop_loss',
                )),
            ],
            options={
                "verbose_name": "Trailing Stop-Loss",
                "verbose_name_plural": "Trailing Stop-Losses",
            },
        ),
        migrations.CreateModel(
            name="TrailingStopEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trail_percent", models.DecimalField(decimal_places=2, max_digits=5)),
                ("reference_price", models.DecimalField(decimal_places=4, max_digits=12)),
                ("triggered_price", models.DecimalField(decimal_places=4, max_digits=12)),
                ("triggered_at", models.DateTimeField(auto_now_add=True)),
                ("notified_at", models.DateTimeField(
                    blank=True, null=True,
                    help_text=(
                        "Zeitpunkt, an dem die Telegram-Nachricht erfolgreich verschickt wurde. "
                        "NULL = noch ausstehend — wird vom notify-price-alarms-Endpoint nachgeholt."
                    ),
                )),
                ("trailing_stop", models.ForeignKey(
                    to='fintech.trailingstoploss', on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True, related_name='events',
                )),
                ("asset", models.ForeignKey(
                    to='fintech.asset', on_delete=django.db.models.deletion.CASCADE,
                    related_name='trailing_stop_events',
                )),
            ],
            options={
                "verbose_name": "Trailing-Stop-Ereignis",
                "verbose_name_plural": "Trailing-Stop-Ereignisse",
                "ordering": ["-triggered_at"],
            },
        ),
    ]
