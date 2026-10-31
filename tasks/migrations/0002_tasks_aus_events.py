from django.db import migrations


def copy_tasks(apps, schema_editor):
    """Übernimmt die bisherigen events.Task-Einträge (inkl. Prompt-Änderungen aus dem Admin) als Cowork-Tasks."""
    OldTask = apps.get_model('events', 'Task')
    Task = apps.get_model('tasks', 'Task')
    for old in OldTask.objects.order_by('id'):
        Task.objects.get_or_create(name=old.name, defaults={'prompt': old.prompt, 'executor': 'cowork'})


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0001_initial'),
        ('events', '0004_tasks_startbestand'),
    ]

    operations = [
        migrations.RunPython(copy_tasks, migrations.RunPython.noop),
    ]
