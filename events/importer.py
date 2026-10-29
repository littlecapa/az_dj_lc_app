"""
JSON-Import für Locations, Artists und Upcoming Events (z.B. Konzertsuche von Claude via MCP).

Format (alle Listen optional, siehe IMPORT_FORMAT):
    {"locations": [...], "artists": [...], "events": [...]}

Regeln:
- Locations/Artists werden über den Namen (Groß-/Kleinschreibung egal) gefunden. Bestehende
  Einträge werden nur ergänzt (leere Felder füllen) — Rating und vorhandene Texte bleiben.
- Events verweisen per Namen auf Location und Artist (aus der DB oder aus derselben Datei).
  Dasselbe Event (Location + Artist + Datum) wird nicht doppelt angelegt, nur ergänzt.
- Alles oder nichts: bei einem Fehler wird nichts gespeichert. dry_run=True prüft nur.
"""

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Artist, Location, UpcomingEvent

IMPORT_FORMAT = {
    "description": "JSON object accepted by the manual events import. All three lists are optional. "
                   "Locations and artists are matched by name (case-insensitive); existing ones are only "
                   "completed, never overwritten. Events reference location and artist by name — either "
                   "existing ones or ones included in the same file. Use ISO dates (YYYY-MM-DD).",
    "example": {
        "locations": [{"name": "Piazza Napoleone, Lucca", "country": "Italien",
                       "info": "Open-Air-Platz, Lucca Summer Festival",
                       "picture_url": "https://…", "rating": 8}],
        "artists": [{"name": "Sting", "rating": 8, "info": "…", "song_url": "https://…"}],
        "events": [{"location": "Arena di Verona", "artist": "Sting", "date": "2027-07-14",
                    "info": "Sting 3.0 Tour", "ticket_url": "https://…"}],
    },
    "fields": {
        "locations": {"name": "required", "country": "required for new locations", "info": "optional",
                      "picture_url": "optional URL", "rating": "optional 1-10, default 8"},
        "artists": {"name": "required", "rating": "optional 1-10, default 8", "info": "optional",
                    "song_url": "optional URL"},
        "events": {"location": "required, location name", "artist": "required, artist name",
                   "date": "required, YYYY-MM-DD", "info": "optional", "ticket_url": "optional URL"},
    },
}

LOCATION_FIELDS = ('country', 'info', 'picture_url', 'rating')
ARTIST_FIELDS = ('rating', 'info', 'song_url')
EVENT_FIELDS = ('info', 'ticket_url')


class _Rollback(Exception):
    pass


def _upsert(model, item, fields, report, kind):
    """Anlegen oder leere Felder ergänzen. Rating wird bei bestehenden Einträgen nie geändert."""
    name = (item.get('name') or '').strip()
    if not name:
        raise ValidationError(f'{kind}: "name" fehlt')
    values = {f: item[f] for f in fields if item.get(f) not in (None, '')}
    obj = model.objects.filter(name__iexact=name).first()
    if obj is None:
        obj = model(name=name, **values)
        obj.full_clean()
        obj.save()
        report['created'][kind].append(name)
        return obj
    changed = [f for f, v in values.items() if f != 'rating' and not getattr(obj, f)]
    for f in changed:
        setattr(obj, f, values[f])
    if changed:
        obj.full_clean()
        obj.save()
        report['updated'][kind].append(obj.name)
    else:
        report['unchanged'][kind].append(obj.name)
    return obj


def _import_event(item, report):
    loc_name, artist_name = (item.get('location') or '').strip(), (item.get('artist') or '').strip()
    label = f'{artist_name} @ {loc_name} {item.get("date")}'
    location = Location.objects.filter(name__iexact=loc_name).first()
    artist = Artist.objects.filter(name__iexact=artist_name).first()
    if location is None:
        raise ValidationError(f'Event {label}: unbekannte Location "{loc_name}"')
    if artist is None:
        raise ValidationError(f'Event {label}: unbekannter Artist "{artist_name}"')
    try:
        date = datetime.date.fromisoformat(str(item.get('date')))
    except ValueError:
        raise ValidationError(f'Event {label}: Datum muss YYYY-MM-DD sein')

    values = {f: item[f] for f in EVENT_FIELDS if item.get(f)}
    event = UpcomingEvent.objects.filter(location=location, artist=artist, date=date).first()
    if event is None:
        event = UpcomingEvent(location=location, artist=artist, date=date, **values)
        event.full_clean()
        event.save()
        report['created']['events'].append(str(event))
        return
    changed = [f for f in values if not getattr(event, f)]
    for f in changed:
        setattr(event, f, values[f])
    if changed:
        event.full_clean()
        event.save()
        report['updated']['events'].append(str(event))
    else:
        report['unchanged']['events'].append(str(event))


def import_events_json(data, dry_run=False):
    """Importiert das geparste JSON. Gibt einen Report zurück; bei Fehlern ist 'errors' gefüllt
    und nichts gespeichert."""
    kinds = ('locations', 'artists', 'events')
    report = {key: {k: [] for k in kinds} for key in ('created', 'updated', 'unchanged')}
    report['errors'] = []
    report['dry_run'] = dry_run

    if not isinstance(data, dict) or not any(k in data for k in kinds):
        report['errors'].append('Erwartet ein JSON-Objekt mit "locations", "artists" und/oder "events".')
        return report

    try:
        with transaction.atomic():
            for kind, handler in (
                ('locations', lambda i: _upsert(Location, i, LOCATION_FIELDS, report, 'locations')),
                ('artists', lambda i: _upsert(Artist, i, ARTIST_FIELDS, report, 'artists')),
                ('events', lambda i: _import_event(i, report)),
            ):
                items = data.get(kind) or []
                if not isinstance(items, list):
                    report['errors'].append(f'"{kind}" muss eine Liste sein')
                    continue
                for item in items:
                    try:
                        if not isinstance(item, dict):
                            raise ValidationError(f'{kind}: Eintrag muss ein Objekt sein')
                        with transaction.atomic():
                            handler(item)
                    except ValidationError as exc:
                        detail = ('; '.join(f'{f}: {", ".join(m)}' for f, m in exc.message_dict.items())
                                  if hasattr(exc, 'error_dict') else '; '.join(exc.messages))
                        name = item.get('name') if isinstance(item, dict) else None
                        report['errors'].append(f'{kind} "{name}": {detail}' if name else detail)
            if dry_run or report['errors']:
                raise _Rollback
    except _Rollback:
        pass
    return report
