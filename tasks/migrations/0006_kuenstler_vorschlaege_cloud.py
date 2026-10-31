from django.db import migrations

NAME = 'Vorschläge für neue Künstler machen'
PROMPT = (
    'Datenquellen: MCP-Server „LC Leisure“ (lc-app-leisure, nur lesend: get_artists, get_categories, '
    'get_suggestions) und „LC Leisure Write“ (lc-app-leisure-write: add_suggestions, log_task_run). Ratings gehen '
    'von 1 bis 10 (10 = sehr gut) und spiegeln meinen persönlichen Geschmack wider. Ist ein MCP-Server nicht '
    'erreichbar, brich ab und melde das, statt mit geratenen Daten weiterzumachen.\n\n'
    'Aufgabe: Schlage mir bis zu 5 neue Künstler vor, die mir gefallen könnten.\n'
    '1. Lies get_artists (mit Kategorie und Rating), get_categories und get_suggestions mit kind=artist (alle Status). '
    'Leite aus den Ratings mein Geschmacksprofil ab — Künstler mit Rating 8 oder höher zählen am meisten, niedrig '
    'bewertete sind eher Gegenbeispiele. Abgelehnte Vorschläge (status rejected) sind ebenfalls Gegenbeispiele.\n'
    '2. Suche im Web nach passenden Künstlern (ähnlicher Stil, ähnliches Publikum, Live-Qualität). Nicht vorschlagen: '
    'Namen, die es schon als Artist oder als Vorschlag gibt — egal mit welchem Status (Namensvergleich ohne '
    'Groß-/Kleinschreibung, auch Schreibvarianten wie „The Killers“/„Killers“ beachten).\n'
    '3. Nur Künstler, die leben und noch live auftreten: Es muss eine aktuelle oder angekündigte Tour bzw. bestätigte '
    'Konzerte in den nächsten 18 Monaten geben. Bevorzugt in Europa (Deutschland, Österreich, Italien, Frankreich, '
    'Schweiz), gern open air. Prüfe das anhand aktueller Tourdaten.\n'
    '4. Für jeden Vorschlag: name (offizielle Schreibweise), category (genau einer der Namen aus get_categories), '
    'info (Deutsch, 1–2 Sätze: warum er passt, „ähnlich wie …“, und die Tour-Info, z. B. „Europa-Tour Sommer 2027, '
    'u. a. Mailand und Wien“), optional song_url (offizieller YouTube- oder Spotify-Link zu einem bekannten Song, '
    'nur wenn geprüft). Kein Rating — das vergebe ich selbst.\n'
    '5. Speichere alle Vorschläge mit einem Aufruf von add_suggestions (kind = artist). Werden welche übersprungen, '
    'ersetze sie höchstens einmal durch andere, insgesamt maximal 5 gespeicherte Vorschläge.\n'
    '6. Melde den Lauf zum Schluss immer mit log_task_run (task = „Vorschläge für neue Künstler machen“): '
    'status success mit message wie „3 neue Vorschläge: A, B, C“ — oder status error mit dem Grund, wenn etwas '
    'schiefging. Auch wenn du nichts Passendes findest, ist das ein success („Keine neuen Vorschläge“).\n\n'
    'Antworte zum Schluss kurz: die gespeicherten Vorschläge mit je einem Satz Begründung und was übersprungen wurde. '
    'Kein JSON ausgeben — bewertet wird in der App unter /leisure/new_artists.'
)


def forwards(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    Task.objects.filter(name=NAME).update(prompt=PROMPT, executor='cloud', interval_hours=168, run_days='0123456')


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0005_prompts_leisure_venues'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
