from django.db import migrations


class Migration(migrations.Migration):
    """
    Macht BlogPost.slug in der DB tatsächlich NULL-fähig.

    Problem: 0009 hat null=True nur im Django-State gesetzt (state_operations),
    in der DB wurde nur der Unique-Index gedroppt. Die Spalte blieb NOT NULL →
    Anlegen eines Posts mit external_url und leerem Slug scheitert mit
    IntegrityError (515, "Cannot insert the value NULL into column 'slug'").
    Lösung: Nur in der DB eventuell noch vorhandene Indizes/Unique-Constraints
    auf slug entfernen (ALTER COLUMN geht sonst nicht) und die Spalte auf NULL
    umstellen. Der Django-State ist bereits korrekt, daher reines RunSQL.
    """

    dependencies = [
        ('homepage', '0012_blogpost_instagram_url'),
    ]

    operations = [
        migrations.RunSQL(
            # Als Liste mit einem Element: ein String würde per sqlparse in
            # Einzel-Statements zerlegt, dann ginge @sql zwischen den Batches verloren.
            sql=[(
                "DECLARE @sql nvarchar(max) = N''; "
                "SELECT @sql += CASE WHEN i.is_unique_constraint = 1 "
                "  THEN N'ALTER TABLE homepage_blogpost DROP CONSTRAINT ' + QUOTENAME(i.name) + N'; ' "
                "  ELSE N'DROP INDEX ' + QUOTENAME(i.name) + N' ON homepage_blogpost; ' END "
                "FROM sys.indexes i "
                "JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
                "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
                "WHERE i.object_id = OBJECT_ID('homepage_blogpost') "
                "  AND c.name = 'slug' AND i.is_primary_key = 0; "
                "EXEC sp_executesql @sql; "
                "ALTER TABLE homepage_blogpost ALTER COLUMN slug nvarchar(50) NULL;"
            )],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
