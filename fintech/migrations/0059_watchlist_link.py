from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0058_currencyclass_add_sar'),
    ]

    operations = [
        migrations.AddField(
            model_name='watchlist',
            name='link',
            field=models.URLField(blank=True, help_text='Optionaler Link zu Zusatzinfos, z. B. Rechner als Google Sheet (Button auf der Watchlist-Seite)', max_length=500),
        ),
    ]
