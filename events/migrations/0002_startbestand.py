from django.db import migrations

# (Name, Land, Info) — alle Locations mit Rating 8
LOCATIONS = [
    ('Lorelei', 'Deutschland',
     'Freilichtbühne Loreley hoch über dem Rhein bei St. Goarshausen (Rheinland-Pfalz).'),
    ('Arena di Verona', 'Italien',
     'Römisches Amphitheater in Verona, im Sommer Opernfestival und große Konzerte.'),
    ("Saline Royale d'Arc-et-Senans (Königliche Saline)", 'Frankreich',
     'UNESCO-Welterbe in Arc-et-Senans (Doubs), Konzerte im Halbrund der Salinengebäude.'),
    ('Wörthersee Ostbucht – Metnitzstrand', 'Österreich',
     'Open-Air-Gelände am Metnitzstrand in der Ostbucht des Wörthersees, Klagenfurt.'),
    ('Piazza Vittorio Alfieri, Asti', 'Italien',
     'Hauptplatz von Asti (Piemont), Bühne des Sommerfestivals Asti Musica.'),
    ('Auditorium Parco della Musica Ennio Morricone, Rom', 'Italien',
     'Konzertkomplex von Renzo Piano in Rom, im Sommer Open-Air-Konzerte in der Cavea.'),
]

# (Name, Rating, Info)
ARTISTS = [
    ('Sting', 8, 'Britischer Sänger und Bassist, ex-The Police.'),
    ('Coldplay', 8, 'Britische Pop-Rock-Band um Chris Martin.'),
    ('Hayley Williams', 6, 'US-Sängerin, Frontfrau von Paramore.'),
    ('Amy Macdonald', 8, 'Schottische Singer-Songwriterin.'),
    ('Paul McCartney', 8, 'Britischer Musiker, ex-The Beatles.'),
    ('John Cleese', 8, 'Britischer Komiker und Schauspieler (Monty Python), Live-Shows.'),
    ('Harry Styles', 7, 'Britischer Popsänger, ex-One Direction.'),
    ('James Blunt', 7, 'Britischer Singer-Songwriter.'),
    ('Santiano', 7, 'Deutsche Band, Shanty-/Folk-Rock aus Flensburg.'),
    ('Rea Garvey', 8, 'Irischer Sänger, ex-Reamonn.'),
    ('Ed Sheeran', 8, 'Britischer Singer-Songwriter.'),
    ('The Killers', 6, 'US-Rockband aus Las Vegas um Brandon Flowers.'),
    ('Pink', 6, 'US-Popsängerin (P!nk), bekannt für akrobatische Live-Shows.'),
]


def seed(apps, schema_editor):
    Location = apps.get_model('events', 'Location')
    Artist = apps.get_model('events', 'Artist')
    for name, country, info in LOCATIONS:
        Location.objects.get_or_create(name=name, defaults={'country': country, 'info': info, 'rating': 8})
    for name, rating, info in ARTISTS:
        Artist.objects.get_or_create(name=name, defaults={'rating': rating, 'info': info})


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
