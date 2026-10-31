from django.db import migrations

# Events → Leisure, Location → Venue (MCP-Server, Tools, JSON-Schlüssel, Texte). Ersetzt wird nur, was im
# Text steht — Prompt-Änderungen aus dem Admin bleiben erhalten.
REPLACEMENTS = [
    ('MCP-Server „LC Events“ (lc-app-events, nur lesend)', 'MCP-Server „LC Leisure“ (lc-app-leisure, nur lesend)'),
    ('get_locations', 'get_venues'),
    ('events-import-', 'leisure-import-'),
    ('Konzert-Locations', 'Konzert-Venues'),
    ('Locations', 'Venues'),
    ('locations', 'venues'),
    ('Location', 'Venue'),
]
RENAMES = {
    'Alle Locations auslesen': 'Alle Venues auslesen',
    'Vorschläge für neue Locations machen': 'Vorschläge für neue Venues machen',
}


def forwards(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    for task in Task.objects.filter(executor='cowork'):
        prompt = task.prompt
        for old, new in REPLACEMENTS:
            prompt = prompt.replace(old, new)
        name = RENAMES.get(task.name, task.name)
        if (prompt, name) != (task.prompt, task.name) and not Task.objects.filter(name=name).exclude(pk=task.pk).exists():
            task.prompt, task.name = prompt, name
            task.save(update_fields=['prompt', 'name'])


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_server_tasks'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
