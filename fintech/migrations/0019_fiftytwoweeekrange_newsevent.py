from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0018_asset_symbol_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='FiftyTwoWeekRange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week52_high', models.DecimalField(decimal_places=4, help_text='52-Wochen-Hoch in Asset-Währung', max_digits=12)),
                ('week52_high_date', models.DateField(blank=True, help_text='Datum, an dem das 52-Wochen-Hoch zuletzt aktualisiert wurde', null=True)),
                ('week52_low', models.DecimalField(decimal_places=4, help_text='52-Wochen-Tief in Asset-Währung', max_digits=12)),
                ('week52_low_date', models.DateField(blank=True, help_text='Datum, an dem das 52-Wochen-Tief zuletzt aktualisiert wurde', null=True)),
                ('fetched_at', models.DateTimeField(default=django.utils.timezone.now, help_text='Zeitpunkt des letzten API-Abrufs')),
                ('asset', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='week52', to='fintech.asset')),
            ],
            options={
                'verbose_name': '52-Wochen-Range',
                'verbose_name_plural': '52-Wochen-Ranges',
            },
        ),
        migrations.CreateModel(
            name='NewsEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('new_high', 'Neues 52W-Hoch'), ('new_low', 'Neues 52W-Tief')], max_length=20)),
                ('old_value', models.DecimalField(blank=True, decimal_places=4, help_text='Bisheriger Extremwert', max_digits=12, null=True)),
                ('new_value', models.DecimalField(decimal_places=4, help_text='Neuer Extremwert', max_digits=12)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assets', models.ManyToManyField(blank=True, related_name='news_events', to='fintech.asset')),
            ],
            options={
                'verbose_name': 'News-Event',
                'verbose_name_plural': 'News-Events',
                'ordering': ['-created_at'],
            },
        ),
    ]
