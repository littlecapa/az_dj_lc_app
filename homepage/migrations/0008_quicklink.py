from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('homepage', '0007_contactmessage_black_listed'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuickLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('url', models.URLField()),
                ('prio', models.PositiveSmallIntegerField(default=2, help_text='1 = hervorgehoben (fett), 2+ = normal. Niedrigere Zahl = weiter oben.')),
                ('category', models.CharField(
                    choices=[
                        ('Chess',   'Chess'),
                        ('Finance', 'Finance'),
                        ('AI',      'AI'),
                        ('Video',   'Video'),
                        ('News',    'News'),
                        ('Misc',    'Misc'),
                        ('Travel',  'Travel'),
                        ('Bonn',    'Bonn'),
                    ],
                    default='Misc',
                    max_length=16,
                )),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Quick Link',
                'verbose_name_plural': 'Quick Links',
                'ordering': ['category', 'prio', 'name'],
            },
        ),
    ]
