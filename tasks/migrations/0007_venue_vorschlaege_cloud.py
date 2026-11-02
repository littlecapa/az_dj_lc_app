from django.db import migrations

NAME = 'Vorschläge für neue Venues machen'
PROMPT = (
    'Datenquellen: MCP-Server „LC Leisure“ (lc-app-leisure, nur lesend: get_venues, get_artists, '
    'get_suggestions) und „LC Leisure Write“ (lc-app-leisure-write: add_suggestions, log_task_run). Ratings gehen '
    'von 1 bis 10 (10 = sehr gut) und spiegeln meinen persönlichen Geschmack wider. Ist ein MCP-Server nicht '
    'erreichbar, brich ab und melde das, statt mit geratenen Daten weiterzumachen.\n\n'
    'Aufgabe: Schlage mir bis zu 5 neue Konzert-Venues vor, die mir gefallen könnten.\n'
    '1. Lies get_venues (mit Land, Info und Rating), get_artists und get_suggestions mit kind=venue (alle Status). '
    'Erkenne, was meine Venues gemeinsam haben (z. B. Open Air, historische Kulisse, Lage am Wasser oder auf '
    'Plätzen, überschaubare Größe, Reiseziel in Europa) — Venues mit Rating 8 oder höher zählen am meisten, niedrig '
    'bewertete und abgelehnte Vorschläge (status rejected) sind Gegenbeispiele.\n'
    '2. Suche im Web nach Venues mit ähnlichem Charakter — vorrangig in Deutschland, Österreich, Italien, Frankreich '
    'und der Schweiz, gern auch in anderen europäischen Ländern. Keine reinen Mehrzweckhallen oder Fußballstadien '
    'ohne besondere Atmosphäre. Nicht vorschlagen: Namen, die es schon als Venue oder als Vorschlag gibt — egal mit '
    'welchem Status (Namensvergleich ohne Groß-/Kleinschreibung, auch Schreibvarianten beachten).\n'
    '3. Nur Venues, an denen regelmäßig Konzerte stattfinden, bevorzugt von Künstlern im Stil meiner Liste '
    '(get_artists). Prüfe das anhand des aktuellen Programms oder angekündigter Konzerte.\n'
    '4. Für jeden Vorschlag: name (offizieller Name, ggf. mit Stadt), country (deutscher Ländername wie in '
    'get_venues), info (Deutsch, 1–2 Sätze: was sie besonders macht, Stadt/Region, ungefähre Kapazität und — falls '
    'gefunden — angekündigte Konzerte von Künstlern aus meiner Liste), optional picture_url (direkter Link zu einem '
    'Bild, z. B. Wikimedia Commons, nur wenn geprüft). Kein Rating — das vergebe ich selbst.\n'
    '5. Speichere alle Vorschläge mit einem Aufruf von add_suggestions (kind = venue). Werden welche übersprungen, '
    'ersetze sie höchstens einmal durch andere, insgesamt maximal 5 gespeicherte Vorschläge.\n'
    '6. Melde den Lauf zum Schluss immer mit log_task_run (task = „Vorschläge für neue Venues machen“): '
    'status success mit message wie „3 neue Vorschläge: A, B, C“ — oder status error mit dem Grund, wenn etwas '
    'schiefging. Auch wenn du nichts Passendes findest, ist das ein success („Keine neuen Vorschläge“).\n\n'
    'Antworte zum Schluss kurz: die gespeicherten Vorschläge mit je einem Satz Begründung und was übersprungen wurde. '
    'Kein JSON ausgeben — bewertet wird in der App unter /leisure/new_venues.'
)


def forwards(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    # Monatlich (Cloud-Routine am 1.), 744 h = längster Monat
    Task.objects.filter(name=NAME).update(prompt=PROMPT, executor='cloud', interval_hours=744, run_days='0123456')


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0006_kuenstler_vorschlaege_cloud'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
