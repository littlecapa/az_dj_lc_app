from django.db import migrations


class Migration(migrations.Migration):
    """Alte Tabellen löschen, nachdem leisure.0002 die Daten übernommen hat. Erst die Tabelle mit den
    Fremdschlüsseln (samt Unique-Constraint) komplett droppen, dann die referenzierten — kein RemoveField,
    das auf MSSQL am Constraint scheitern kann."""

    dependencies = [
        ('events', '0005_task_nach_tasks_app'),
        ('leisure', '0002_daten_aus_events'),  # Daten erst kopieren, dann löschen
    ]

    operations = [
        migrations.DeleteModel(name='UpcomingEvent'),
        migrations.DeleteModel(name='Artist'),
        migrations.DeleteModel(name='Location'),
    ]
