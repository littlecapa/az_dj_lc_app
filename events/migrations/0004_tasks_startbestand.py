from django.db import migrations

QUELLE = (
    'Datenquelle ist der MCP-Server „LC Events“ (lc-app-events, nur lesend) mit den Tools get_artists, '
    'get_locations, get_upcoming_events und get_import_format. Ratings gehen von 1 bis 10 (10 = sehr gut) '
    'und spiegeln meinen persönlichen Geschmack wider. Ist der MCP-Server nicht erreichbar, brich ab und '
    'melde das, statt mit geratenen Daten weiterzumachen.'
)

JSON_REGELN = (
    'Ergebnis-Format: Rufe get_import_format auf und liefere genau ein JSON-Objekt in diesem Format '
    '(nur die Listen, die du brauchst). Speichere es als Datei events-import-<heutiges Datum YYYY-MM-DD>-<kurzer '
    'Task-Name>.json im Arbeitsordner und gib es zusätzlich als ```json-Block aus — ich importiere es manuell.\n'
    'Regeln für das JSON:\n'
    '- Namen von bestehenden Künstlern und Locations exakt so schreiben, wie get_artists / get_locations sie liefern.\n'
    '- Keine Einträge, die es schon gibt (Namensvergleich ohne Groß-/Kleinschreibung, auch Schreibvarianten wie '
    '„The Killers“/„Killers“ beachten).\n'
    '- Links (picture_url, song_url, ticket_url) nur, wenn du sie tatsächlich gefunden und geprüft hast — '
    'lieber weglassen als raten. Keine Wiederverkäufer (Viagogo, StubHub o.ä.) als ticket_url.\n'
    '- Texte (info) auf Deutsch, kurz (1–2 Sätze).\n'
    '- Wenn du nichts Neues findest, liefere kein leeres JSON, sondern schreibe nur „Keine neuen Vorschläge“.'
)

TASKS = [
    ('Alle Künstler auslesen',
     f'{QUELLE}\n\n'
     'Aufgabe: Lies mit get_artists alle Künstler aus und gib mir eine Übersicht als Markdown-Tabelle mit den '
     'Spalten Name, Rating, Info und Song-Link, sortiert nach Rating (höchstes zuerst), bei gleichem Rating '
     'alphabetisch. Hole zusätzlich mit get_upcoming_events die bekannten kommenden Konzerte und ergänze eine '
     'Spalte „Nächstes Konzert“ (Datum und Location, sonst „–“).\n\n'
     'Schließe mit zwei, drei Sätzen ab: Anzahl Künstler, Verteilung der Ratings und welche Künstler ohne '
     'bekanntes kommendes Konzert sind. Nichts im Web suchen, nichts erfinden, kein JSON erzeugen.'),

    ('Vorschläge für neue Künstler machen',
     f'{QUELLE}\n\n'
     'Aufgabe: Schlage mir bis zu 5 neue Künstler vor, die mir gefallen könnten.\n'
     '1. Lies mit get_artists alle Künstler und leite aus den Ratings mein Geschmacksprofil ab — Künstler mit '
     'Rating 8 oder höher zählen am meisten, niedrig bewertete sind eher Gegenbeispiele.\n'
     '2. Suche im Web nach passenden Künstlern (ähnlicher Stil, ähnliches Publikum, Live-Qualität), die es noch '
     'nicht in der Liste gibt.\n'
     '3. Bevorzuge Künstler, die in den nächsten 12 Monaten in Europa live spielen — bevorzugt in Deutschland, '
     'Österreich, Italien, Frankreich oder der Schweiz, gern open air. Prüfe das anhand aktueller Tourdaten.\n'
     '4. Setze für jeden Vorschlag ein geschätztes rating (wie gut er zu meinem Profil passt, maximal 8) und '
     'begründe es in info („ähnlich wie …, weil …“). song_url: offizieller YouTube- oder Spotify-Link zu einem '
     'bekannten Song.\n'
     '5. Hat ein vorgeschlagener Künstler bereits bestätigte Konzerte, nimm sie als events mit auf; fehlt die '
     'Location noch, lege sie unter locations an (mit country).\n\n'
     f'{JSON_REGELN}\n\n'
     'Fasse vor dem JSON jeden Vorschlag in einem Satz zusammen.'),

    ('Alle Locations auslesen',
     f'{QUELLE}\n\n'
     'Aufgabe: Lies mit get_locations alle Locations aus und gib mir eine Übersicht als Markdown-Tabelle mit '
     'den Spalten Name, Land, Rating, Info und Bild-Link, gruppiert nach Land und innerhalb des Landes nach '
     'Rating (höchstes zuerst). Hole zusätzlich mit get_upcoming_events die bekannten kommenden Konzerte und '
     'ergänze eine Spalte „Kommende Konzerte“ (Anzahl und nächstes Datum mit Künstler, sonst „–“).\n\n'
     'Schließe mit zwei, drei Sätzen ab: Anzahl Locations je Land und welche Locations ohne bekanntes kommendes '
     'Konzert sind. Nichts im Web suchen, nichts erfinden, kein JSON erzeugen.'),

    ('Vorschläge für neue Locations machen',
     f'{QUELLE}\n\n'
     'Aufgabe: Schlage mir bis zu 5 neue Konzert-Locations vor.\n'
     '1. Lies mit get_locations alle Locations und erkenne, was sie gemeinsam haben (z.B. Open Air, historische '
     'Kulisse, Lage am Wasser oder auf Plätzen, überschaubare Größe, Reiseziel in Europa).\n'
     '2. Suche im Web nach Locations mit ähnlichem Charakter, die es noch nicht in der Liste gibt — vorrangig in '
     'Deutschland, Österreich, Italien, Frankreich und der Schweiz, gern auch andere europäische Länder.\n'
     '3. Bevorzuge Locations, an denen regelmäßig Konzerte von Künstlern im Stil meiner Liste stattfinden '
     '(get_artists). Keine reinen Mehrzweckhallen oder Fußballstadien ohne besondere Atmosphäre.\n'
     '4. Für jede Location: name (offizieller Name, ggf. mit Stadt), country (deutscher Ländername wie in der '
     'Liste), info (was sie besonders macht, Stadt/Region, ungefähre Kapazität), optional picture_url (direkter '
     'Link zu einem Bild, z.B. Wikimedia Commons), rating als Schätzung, wie gut sie zu meinen Favoriten passt '
     '(maximal 8).\n'
     '5. Sind dort bereits Konzerte von Künstlern aus meiner Liste angekündigt, nimm sie als events mit auf.\n\n'
     f'{JSON_REGELN}\n\n'
     'Fasse vor dem JSON jeden Vorschlag in einem Satz zusammen.'),

    ('Vorschläge für weitere Upcoming Events machen',
     f'{QUELLE}\n\n'
     'Aufgabe: Finde neue, offiziell angekündigte Konzerte meiner Künstler und an meinen Locations.\n'
     '1. Lies get_artists, get_locations und get_upcoming_events (ohne Parameter = ab heute). Bereits bekannte '
     'Konzerte (gleicher Künstler, gleiche Location, gleiches Datum) nicht noch einmal vorschlagen.\n'
     '2. Suche für jeden Künstler im Web nach Tourdaten der nächsten 18 Monate, am besten auf der offiziellen '
     'Website, bei Ticketmaster/Eventim oder dem Veranstalter. Berücksichtige nur Konzerte in Europa, vorrangig '
     'Deutschland, Österreich, Italien, Frankreich und Schweiz.\n'
     '3. Suche außerdem für jede Location nach dem angekündigten Programm (z.B. Festivals wie Asti Musica, die '
     'Konzertsaison der Arena di Verona) und nimm Konzerte von Künstlern auf, die zu meiner Liste passen. Neue '
     'Künstler dabei unter artists anlegen (rating als Schätzung, maximal 7, mit Begründung in info).\n'
     '4. Konzerte an Locations, die nicht in meiner Liste sind, nur bei Künstlern mit Rating 7 oder höher '
     'aufnehmen — und die Location dann unter locations anlegen (country, info, rating als Schätzung).\n'
     '5. Nur bestätigte Termine mit konkretem Datum, keine Gerüchte. In info: Tour- oder Festivalname, '
     'Stadt und ob schon ausverkauft. ticket_url: offizieller Ticketlink.\n'
     '6. Sortiere die events nach Datum.\n\n'
     f'{JSON_REGELN}\n\n'
     'Fasse vor dem JSON zusammen: wie viele neue Konzerte, die drei interessantesten (hohes Künstler- und '
     'Location-Rating) und bei welchen Künstlern du nichts gefunden hast.'),
]


def seed(apps, schema_editor):
    Task = apps.get_model('events', 'Task')
    for name, prompt in TASKS:
        Task.objects.get_or_create(name=name, defaults={'prompt': prompt})


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0003_task'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
