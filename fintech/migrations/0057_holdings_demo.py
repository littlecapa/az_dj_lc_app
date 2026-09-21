from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0056_newsarticle'),
    ]

    operations = [
        migrations.AddField(
            model_name='holdings',
            name='demo',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Diese Position im öffentlichen, login-freien Demo-Bereich '
                    '(/demo/fintech/) anzeigen.'
                ),
            ),
        ),
    ]
