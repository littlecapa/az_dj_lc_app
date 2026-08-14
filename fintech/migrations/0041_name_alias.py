"""
Migration 0041: NameAlias — Synonym-Tabelle für den Namensabgleich

Ersetzt die bisher in name_matching.py hartkodierte _KNOWN_ALIASES-Liste
durch eine Admin-pflegbare DB-Tabelle. Übernimmt die zwei bisher bekannten
Fälle als Startdaten: BMW (Wikipedia-DAX nennt die Aktie schlicht "BMW")
und Exxonmobil (companiesmarketcap.com schreibt den Namen zusammen).
"""
from django.db import migrations, models

SEED_ALIASES = [
    ("BMW", "Motoren Werke"),
    ("Exxonmobil", "Exxon Mobil"),
]


def add_seed_aliases(apps, schema_editor):
    NameAlias = apps.get_model('fintech', 'NameAlias')
    for external_name, search_term in SEED_ALIASES:
        NameAlias.objects.update_or_create(
            external_name=external_name,
            defaults={'search_term': search_term},
        )


def remove_seed_aliases(apps, schema_editor):
    NameAlias = apps.get_model('fintech', 'NameAlias')
    NameAlias.objects.filter(
        external_name__in=[name for name, _ in SEED_ALIASES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('fintech', '0040_em_digital_leaders_and_dlf_manual_holdings'),
    ]

    operations = [
        migrations.CreateModel(
            name='NameAlias',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_name', models.CharField(
                    max_length=100, unique=True,
                    help_text='Name, wie er in der externen Quelle steht, z.B. "BMW".',
                )),
                ('search_term', models.CharField(
                    max_length=100,
                    help_text=(
                        'Ersatz-Suchbegriff, dessen Wörter stattdessen gegen den gehaltenen '
                        'Namen geprüft werden, z.B. "Motoren Werke". Bewusst knapp halten, damit '
                        'es auch mit unterschiedlich abgekürzten Schreibweisen im eigenen '
                        'Bestand funktioniert.'
                    ),
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': "Namens-Synonym",
                'verbose_name_plural': "Namens-Synonyme",
                'ordering': ['external_name'],
            },
        ),
        migrations.RunPython(add_seed_aliases, remove_seed_aliases),
    ]
