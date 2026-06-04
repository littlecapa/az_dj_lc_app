from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('homepage', '0008_quicklink'),
    ]

    operations = [
        # SQL Server: bestehenden Unique-Index explizit droppen bevor AlterField
        migrations.RunSQL(
            sql="IF EXISTS (SELECT name FROM sys.indexes WHERE name = 'homepage_blogpost_slug_ca3a29db') "
                "DROP INDEX homepage_blogpost_slug_ca3a29db ON homepage_blogpost;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='blogpost',
            name='slug',
            field=models.SlugField(
                blank=True,
                null=True,
                help_text='Auto-generated from headline if empty. Used to find the blog template.',
            ),
        ),
    ]
