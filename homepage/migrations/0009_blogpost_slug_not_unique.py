from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Entfernt den UNIQUE-Constraint vom BlogPost.slug-Feld.

    Problem: Der mssql-Backend versucht nach AlterField einen neuen Index
    mit demselben Namen anzulegen → Konflikt.
    Lösung: SeparateDatabaseAndState — DROP INDEX nur in der DB,
    AlterField nur im Django-State (kein SQL).
    """

    dependencies = [
        ('homepage', '0008_quicklink'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Nur in der DB: Unique-Index droppen
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "IF EXISTS ("
                        "  SELECT 1 FROM sys.indexes "
                        "  WHERE name = 'homepage_blogpost_slug_ca3a29db' "
                        "  AND object_id = OBJECT_ID('homepage_blogpost')"
                        ") "
                        "DROP INDEX homepage_blogpost_slug_ca3a29db "
                        "ON homepage_blogpost;"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            # Nur im Django-State: Feld als non-unique markieren
            state_operations=[
                migrations.AlterField(
                    model_name='blogpost',
                    name='slug',
                    field=models.SlugField(
                        blank=True,
                        null=True,
                        help_text='Auto-generated from headline if empty. Used to find the blog template.',
                    ),
                ),
            ],
        ),
    ]
