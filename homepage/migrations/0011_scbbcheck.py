from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('homepage', '0010_chessposition'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScbbCheck',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('checked_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('status_code', models.PositiveSmallIntegerField(blank=True, help_text='HTTP-Statuscode, leer bei Verbindungsfehler/Timeout.', null=True)),
                ('response_time_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('error', models.CharField(blank=True, max_length=255)),
            ],
            options={
                'verbose_name': 'SCBB Check',
                'verbose_name_plural': 'SCBB Checks',
                'ordering': ['-checked_at'],
            },
        ),
    ]
