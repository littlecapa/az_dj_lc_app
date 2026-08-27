from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0048_pricealarm_pricealarmevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="pricealarmevent",
            name="notified_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "Zeitpunkt, an dem die Telegram-Nachricht erfolgreich verschickt wurde. "
                    "NULL = noch ausstehend — wird vom notify-price-alarms-Endpoint nachgeholt "
                    "(z.B. wenn das Event aus einem Prozess ohne Telegram-Konfiguration entstand, "
                    "etwa dem update_prices-Lauf auf GitHub Actions)."
                ),
            ),
        ),
    ]
