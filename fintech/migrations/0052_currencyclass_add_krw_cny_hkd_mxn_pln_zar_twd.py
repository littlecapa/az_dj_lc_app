from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0051_activate_trailing_stops_default_batch"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="currency",
            field=models.CharField(
                max_length=3,
                default="EUR",
                choices=[
                    ("EUR", "EUR"), ("USD", "USD"), ("CHF", "CHF"),
                    ("GBP", "GBP"), ("GBp", "GBp"), ("JPY", "JPY"),
                    ("NOK", "NOK"), ("CAD", "CAD"), ("DKK", "DKK"),
                    ("SEK", "SEK"), ("AUD", "AUD"), ("KRW", "KRW"),
                    ("CNY", "CNY"), ("HKD", "HKD"), ("MXN", "MXN"),
                    ("PLN", "PLN"), ("ZAR", "ZAR"), ("ZAc", "ZAc"),
                    ("TWD", "TWD"),
                ],
                help_text="Währung als ISO-Code (EUR, USD, etc.)",
            ),
        ),
    ]
