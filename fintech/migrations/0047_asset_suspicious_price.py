from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fintech", "0046_asset_price_fetch_failing_since"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="suspicious_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=12,
                null=True,
                help_text=(
                    "Abgelehnter Kurs, der zu stark vom letzten current_price abweicht "
                    "(Plausibilitäts-Check). Bleibt dieser Wert über "
                    "suspicious_price_since hinweg >24h konsistent (statt bei jedem Lauf "
                    "zufällig anders), gilt er als echter Kurssprung (Split, Rallye, "
                    "Crash) statt als einmaliger Scraping-Fehler und wird automatisch "
                    "übernommen."
                ),
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="suspicious_price_since",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Zeitpunkt, seit dem suspicious_price konsistent gemeldet wird.",
            ),
        ),
    ]
