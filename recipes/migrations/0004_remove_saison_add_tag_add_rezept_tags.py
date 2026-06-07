from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recipes', '0003_rezept_foto_url'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
            ],
            options={
                'verbose_name': 'Tag',
                'verbose_name_plural': 'Tags',
                'ordering': ['name'],
            },
        ),
        migrations.RemoveField(
            model_name='rezept',
            name='saison',
        ),
        migrations.AddField(
            model_name='rezept',
            name='tags',
            field=models.ManyToManyField(blank=True, related_name='rezepte', to='recipes.tag'),
        ),
    ]
