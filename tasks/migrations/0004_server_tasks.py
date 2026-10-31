from django.db import migrations

SERVER_TASKS = [
    ('Kurse aktualisieren', 'update_prices', 24, '012345',
     'Aktualisiert die Kurse aller Assets (python manage.py update_prices). Läuft per GitHub Actions '
     '(update_prices.yml) Mo–Fr 4x täglich und samstags 1x.'),
    ('News aktualisieren', 'update_news', 24, '0123456',
     'Holt News für Aktien über der Look-Through-Schwelle (python manage.py update_news). Läuft per GitHub '
     'Actions (update_news.yml) täglich.'),
    ('ETF-Holdings aktualisieren', 'update_etf_holdings', 168, '0123456',
     'Aktualisiert die Top-Holdings aller gehaltenen ETFs/Fonds (python manage.py update_etf_holdings). Läuft '
     'per GitHub Actions (update_etf_holdings.yml) montags.'),
]


def seed(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    for name, command, interval, run_days, prompt in SERVER_TASKS:
        Task.objects.get_or_create(name=name, defaults={
            'executor': 'server', 'command': command, 'interval_hours': interval, 'run_days': run_days,
            'prompt': prompt})


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0003_command_run_days'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
