from django.db import migrations

CATEGORIES = ['Pop', 'Rock', 'Singer-Songwriter', 'Folk/Shanty', 'Comedy', 'Klassik/Oper']
ARTIST_CATEGORIES = {
    'Sting': 'Pop', 'Coldplay': 'Rock', 'Hayley Williams': 'Rock', 'Amy Macdonald': 'Singer-Songwriter',
    'Paul McCartney': 'Rock', 'John Cleese': 'Comedy', 'Harry Styles': 'Pop', 'James Blunt': 'Singer-Songwriter',
    'Santiano': 'Folk/Shanty', 'Rea Garvey': 'Pop', 'Ed Sheeran': 'Singer-Songwriter', 'The Killers': 'Rock',
    'Pink': 'Pop',
}


def seed(apps, schema_editor):
    Category, Artist = apps.get_model('leisure', 'Category'), apps.get_model('leisure', 'Artist')
    categories = {name: Category.objects.get_or_create(name=name)[0] for name in CATEGORIES}
    for artist, category in ARTIST_CATEGORIES.items():
        Artist.objects.filter(name=artist, category__isnull=True).update(category=categories[category])


class Migration(migrations.Migration):

    dependencies = [
        ('leisure', '0003_category_suggestion'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
