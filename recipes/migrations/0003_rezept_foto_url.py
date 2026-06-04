from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recipes', '0002_remove_zeit_new_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='rezept',
            name='foto_url',
            field=models.URLField(
                blank=True,
                null=True,
                verbose_name='Foto-URL',
                help_text='Direkter Bild-Link, z.B. Google Drive: https://drive.google.com/uc?id=FILE_ID',
            ),
        ),
    ]
