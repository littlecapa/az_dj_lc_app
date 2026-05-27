from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0007_alter_asset_asset_class'),
    ]

    operations = [
        migrations.AddField(
            model_name='holdings',
            name='not_for_sale',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Position aktuell nicht zum Verkauf vorgesehen '
                    '(z. B. VL-Sperre, Unternehmensaktien, emotionale Gründe)'
                ),
            ),
        ),
    ]
