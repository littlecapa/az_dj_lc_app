from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0019_fiftytwoweeekrange_newsevent'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week52_no_date_ttl_days', models.PositiveIntegerField(
                    default=7,
                    verbose_name='52W-Range TTL ohne Datum (Tage)',
                    help_text=(
                        'Wie viele Tage ein 52W-Range-Eintrag ohne Datum (Yahoo liefert keins) '
                        'als gültig gilt, bevor er neu abgerufen wird.'
                    ),
                )),
            ],
            options={
                'verbose_name': 'Fintech-Konfiguration',
                'verbose_name_plural': 'Fintech-Konfiguration',
            },
        ),
    ]
