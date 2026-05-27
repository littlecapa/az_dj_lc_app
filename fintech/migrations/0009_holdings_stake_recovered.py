from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0008_holdings_not_for_sale'),
    ]

    operations = [
        migrations.AddField(
            model_name='holdings',
            name='stake_recovered',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Original stake already recovered through profit-taking — '
                    "remaining position is essentially 'free'."
                ),
            ),
        ),
    ]
