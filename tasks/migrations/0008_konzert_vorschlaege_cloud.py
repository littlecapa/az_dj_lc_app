from django.db import migrations

NAME = 'Vorschläge für weitere Upcoming Events machen'
PROMPT = (
    'Datenquellen: MCP-Server „LC Leisure“ (lc-app-leisure, nur lesend: get_artists, get_venues, '
    'get_upcoming_events, get_suggestions) und „LC Leisure Write“ (lc-app-leisure-write: add_suggestions, '
    'log_task_run). Ratings gehen von 1 bis 10 (10 = sehr gut) und spiegeln meinen persönlichen Geschmack wider. Ist '
    'ein MCP-Server nicht erreichbar, brich ab und melde das, statt mit geratenen Daten weiterzumachen.\n\n'
    'Aufgabe: Finde neue, offiziell angekündigte Konzerte meiner Artists für die nächsten 18 Monate.\n'
    '1. Lies get_artists, get_venues, get_upcoming_events (ohne Parameter = ab heute) und get_suggestions mit '
    'kind=event und kind=venue (alle Status). Bekannte Konzerte und schon vorgeschlagene, übernommene oder verworfene '
    'Konzerte (gleicher Artist, gleiche Venue, gleiches Datum) nicht noch einmal vorschlagen. Venues mit status '
    'rejected sind tabu.\n'
    '2. Suche für jeden Artist im Web nach Tourdaten, am besten auf der offiziellen Website, bei Ticketmaster/Eventim '
    'oder beim Veranstalter. Suche außerdem für jede Venue nach dem angekündigten Programm (z. B. Festivals wie Asti '
    'Musica, die Konzertsaison der Arena di Verona) und nimm Konzerte von Artists aus meiner Liste auf.\n'
    '3. Aufnehmen:\n'
    '   a) Konzerte von Artists aus meiner Liste an Venues aus meiner Liste — überall.\n'
    '   b) Konzerte von Artists mit Rating 7 oder höher an anderen Orten, aber nur in Deutschland, Österreich, der '
    'Schweiz, Italien oder Frankreich und nur an Orten mit Charakter (Open Air, historische Kulisse, besondere Lage). '
    'Keine reinen Mehrzweckhallen oder Fußballstadien ohne besondere Atmosphäre. Für diese neue Venue zusätzlich '
    'country (deutscher Ländername) und venue_info (Deutsch: was sie besonders macht, Stadt, ungefähre Kapazität) '
    'angeben — sie landet dann als Venue-Vorschlag bei mir.\n'
    '   Künstler, die nicht in get_artists stehen, nicht aufnehmen.\n'
    '4. Nur bestätigte Termine mit konkretem Datum, keine Gerüchte. Für jedes Konzert: artist (exakt wie in '
    'get_artists), venue (exakt wie in get_venues, bei neuen Venues der offizielle Name, ggf. mit Stadt), date '
    '(YYYY-MM-DD), info (Deutsch, kurz: Tour- oder Festivalname, Stadt, ob schon ausverkauft), optional ticket_url '
    '(offizieller Ticketlink, nur wenn geprüft).\n'
    '5. Speichere alle Konzerte mit add_suggestions (kind = event), höchstens 30 pro Aufruf; bei mehr Treffern in '
    'mehreren Aufrufen. Prüfe die skipped-Liste: Tippfehler in Namen korrigieren und einmal neu senden, den Rest '
    'akzeptieren.\n'
    '6. Melde den Lauf zum Schluss immer mit log_task_run (task = „Vorschläge für weitere Upcoming Events machen“): '
    'status success mit message wie „12 neue Konzerte, 2 neue Venues“ — oder status error mit dem Grund, wenn etwas '
    'schiefging. Auch wenn du nichts Neues findest, ist das ein success („Keine neuen Konzerte“).\n\n'
    'Antworte zum Schluss kurz: wie viele neue Konzerte, die drei interessantesten (hohes Artist- und Venue-Rating), '
    'welche neuen Venues dabei sind und bei welchen Artists du nichts gefunden hast. Kein JSON ausgeben — bewertet '
    'wird in der App unter /leisure/new_events.'
)


def forwards(apps, schema_editor):
    Task = apps.get_model('tasks', 'Task')
    Task.objects.filter(name=NAME).update(prompt=PROMPT, executor='cloud', interval_hours=168, run_days='0123456')


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0007_venue_vorschlaege_cloud'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
