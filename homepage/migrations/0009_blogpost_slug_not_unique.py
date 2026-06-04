from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('homepage', '0008_quicklink'),
    ]

    operations = [
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
