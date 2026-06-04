from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Rezept',
            fields=[
                ('id',        models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name',      models.CharField(max_length=200)),
                ('kategorie', models.CharField(
                    choices=[
                        ('fruehstueck', 'Frühstück'),
                        ('suppen',      'Suppen'),
                        ('vegetarisch', 'Vegetarisch'),
                        ('fleisch',     'Fleisch & Fisch'),
                        ('pasta',       'Pasta & Reis'),
                        ('backen',      'Backen'),
                        ('dessert',     'Desserts'),
                        ('snacks',      'Snacks & Dips'),
                        ('getraenke',   'Getränke'),
                    ],
                    default='vegetarisch',
                    max_length=50,
                )),
                ('aufwand',   models.CharField(
                    choices=[('niedrig', 'Niedrig'), ('mittel', 'Mittel'), ('hoch', 'Hoch')],
                    default='niedrig',
                    max_length=20,
                )),
                ('quelle',    models.CharField(blank=True, max_length=100)),
                ('zutaten',   models.TextField(blank=True)),
                ('zeit',      models.IntegerField(blank=True, null=True)),
                ('saison',    models.CharField(default='Ganzjährig', max_length=50)),
                ('notiz',     models.TextField(blank=True)),
                ('link',      models.URLField(blank=True)),
                ('liebling',  models.BooleanField(default=False)),
                ('foto',      models.ImageField(blank=True, null=True, upload_to='rezepte/')),
                ('erstellt',  models.DateTimeField(auto_now_add=True)),
                ('geaendert', models.DateTimeField(auto_now=True)),
                ('user',      models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rezepte',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Rezept',
                'verbose_name_plural': 'Rezepte',
                'ordering': ['name'],
            },
        ),
    ]
