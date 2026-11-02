"""Vorschläge (Suggestion): Anlegen durch Claude (MCP add_suggestions) und Entscheidung im Formular."""

import datetime

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone

from .models import Artist, Category, Suggestion, UpcomingEvent, Venue

MAX_PER_CALL = 5
MAX_EVENTS_PER_CALL = 30
TOP_ARTIST_RATING = 7  # Konzerte an fremden Venues nur für Artists ab diesem Rating

# Je Art: Zielmodell und das optionale Link-Feld (landet im payload).
KINDS = {
    Suggestion.Kind.ARTIST: {'model': Artist, 'label': 'Artist', 'url_field': 'song_url'},
    Suggestion.Kind.VENUE: {'model': Venue, 'label': 'Venue', 'url_field': 'picture_url'},
}


def _skip_reason(kind, name):
    spec = KINDS[kind]
    if spec['model'].objects.filter(name__iexact=name).exists():
        return f'gibt es schon als {spec["label"]}'
    existing = Suggestion.objects.filter(kind=kind, name__iexact=name).first()
    if existing:
        return {Suggestion.Status.PENDING: 'ist schon vorgeschlagen und noch offen',
                Suggestion.Status.ACCEPTED: 'wurde schon übernommen',
                Suggestion.Status.REJECTED: 'wurde abgelehnt (Blacklist)'}[existing.status]
    return None


def add_suggestions(kind, items):
    """Legt bis zu MAX_PER_CALL Vorschläge an (Artists brauchen eine Kategorie, Venues ein Land).
    Bekannte, offene oder abgelehnte Namen werden übersprungen."""
    if kind == Suggestion.Kind.EVENT:
        return add_event_suggestions(items)
    spec = KINDS[kind]
    created, skipped = [], []
    categories = {c.name.lower(): c for c in Category.objects.all()}
    for index, item in enumerate(items):
        name = (item.get('name') or '').strip() if isinstance(item, dict) else ''
        if index >= MAX_PER_CALL:
            skipped.append({'name': name, 'reason': f'maximal {MAX_PER_CALL} Vorschläge pro Aufruf'})
            continue
        if not name:
            skipped.append({'name': name, 'reason': '"name" fehlt'})
            continue
        reason = _skip_reason(kind, name)
        payload, category = {}, None
        if kind == Suggestion.Kind.ARTIST:
            category = categories.get((item.get('category') or '').strip().lower())
            if not reason and category is None:
                reason = f'unbekannte Kategorie "{item.get("category")}", erlaubt: {", ".join(c.name for c in categories.values())}'
        else:
            payload['country'] = (item.get('country') or '').strip()
            if not reason and not payload['country']:
                reason = '"country" fehlt'
        url = (item.get(spec['url_field']) or '').strip()
        if not reason and url:
            try:
                URLValidator()(url)
                payload[spec['url_field']] = url
            except ValidationError:
                reason = f'{spec["url_field"]} ist keine gültige URL: {url}'
        if reason:
            skipped.append({'name': name, 'reason': reason})
            continue
        Suggestion.objects.create(kind=kind, name=name, category=category,
                                  info=(item.get('info') or '').strip(), payload=payload)
        created.append(name)
    return {'created': created, 'skipped': skipped}


def _event_skip_reason(item, today):
    """Prüft ein Konzert und liefert (Grund, Artist, Venue-Name, Datum); Grund None = in Ordnung."""
    artist = Artist.objects.filter(name__iexact=(item.get('artist') or '').strip()).first()
    if artist is None:
        return f'unbekannter Artist "{item.get("artist")}" (nur Artists aus get_artists)', None, '', None
    try:
        date = datetime.date.fromisoformat((item.get('date') or '').strip())
    except ValueError:
        return f'date muss YYYY-MM-DD sein: {item.get("date")}', artist, '', None
    if date < today:
        return 'liegt in der Vergangenheit', artist, '', date
    venue_name = (item.get('venue') or '').strip()
    if not venue_name:
        return '"venue" fehlt', artist, '', date
    venue = Venue.objects.filter(name__iexact=venue_name).first()
    if venue:
        if UpcomingEvent.objects.filter(artist=artist, venue=venue, date=date).exists():
            return 'gibt es schon als Upcoming Event', artist, venue.name, date
        return None, artist, venue.name, date
    if artist.rating < TOP_ARTIST_RATING:
        return f'fremde Venue nur bei Artists mit Rating ab {TOP_ARTIST_RATING}', artist, venue_name, date
    if Suggestion.objects.filter(kind=Suggestion.Kind.VENUE, name__iexact=venue_name,
                                 status=Suggestion.Status.REJECTED).exists():
        return 'Venue steht auf der Blacklist', artist, venue_name, date
    if not (item.get('country') or '').strip():
        return '"country" fehlt (Pflicht bei Venues, die es noch nicht gibt)', artist, venue_name, date
    return None, artist, venue_name, date


def add_event_suggestions(items):
    """Konzert-Vorschläge: nur bekannte Artists; an einer fremden Venue nur Top-Artists, die Venue wird dann
    zusätzlich als Venue-Vorschlag angelegt. Verworfene Konzerte werden nicht erneut angenommen."""
    created, skipped = [], []
    today = timezone.localdate()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            skipped.append({'name': '', 'reason': 'Eintrag muss ein Objekt sein'})
            continue
        label = f'{item.get("artist")} @ {item.get("venue")}, {item.get("date")}'
        if index >= MAX_EVENTS_PER_CALL:
            skipped.append({'name': label, 'reason': f'maximal {MAX_EVENTS_PER_CALL} Konzerte pro Aufruf'})
            continue
        reason, artist, venue_name, date = _event_skip_reason(item, today)
        name = f'{artist.name} @ {venue_name}, {date.isoformat()}' if not reason else label
        existing = None if reason else Suggestion.objects.filter(kind=Suggestion.Kind.EVENT, name__iexact=name).first()
        if existing:
            reason = {Suggestion.Status.PENDING: 'ist schon vorgeschlagen und noch offen',
                      Suggestion.Status.ACCEPTED: 'wurde schon übernommen',
                      Suggestion.Status.REJECTED: 'wurde schon verworfen'}[existing.status]
        ticket_url = (item.get('ticket_url') or '').strip()
        if not reason and ticket_url:
            try:
                URLValidator()(ticket_url)
            except ValidationError:
                reason = f'ticket_url ist keine gültige URL: {ticket_url}'
        if reason:
            skipped.append({'name': name, 'reason': reason})
            continue
        payload = {'artist': artist.name, 'venue': venue_name, 'date': date.isoformat()}
        if ticket_url:
            payload['ticket_url'] = ticket_url
        if not Venue.objects.filter(name__iexact=venue_name).exists():
            payload['new_venue'] = True
            if not Suggestion.objects.filter(kind=Suggestion.Kind.VENUE, name__iexact=venue_name).exists():
                Suggestion.objects.create(kind=Suggestion.Kind.VENUE, name=venue_name,
                                          info=(item.get('venue_info') or '').strip(),
                                          payload={'country': item['country'].strip()})
        Suggestion.objects.create(kind=Suggestion.Kind.EVENT, name=name, info=(item.get('info') or '').strip(),
                                  payload=payload)
        created.append(name)
    return {'created': created, 'skipped': skipped}


def _accept_event(suggestion):
    data = suggestion.payload
    venue = Venue.objects.filter(name__iexact=data['venue']).first()
    if venue is None:
        raise ValidationError(f'{suggestion.name}: Venue „{data["venue"]}“ zuerst unter Neue Venues übernehmen')
    artist = Artist.objects.get(name__iexact=data['artist'])
    UpcomingEvent.objects.get_or_create(
        artist=artist, venue=venue, date=datetime.date.fromisoformat(data['date']),
        defaults={'info': suggestion.info, 'ticket_url': data.get('ticket_url', '')})


def _accept(suggestion, rating):
    if suggestion.kind == Suggestion.Kind.EVENT:
        _accept_event(suggestion)
    elif suggestion.kind == Suggestion.Kind.ARTIST:
        if not Artist.objects.filter(name__iexact=suggestion.name).exists():
            Artist.objects.create(name=suggestion.name, rating=rating, category=suggestion.category,
                                  info=suggestion.info, song_url=suggestion.payload.get('song_url', ''))
    elif not Venue.objects.filter(name__iexact=suggestion.name).exists():
        Venue.objects.create(name=suggestion.name, rating=rating, country=suggestion.payload.get('country', ''),
                             info=suggestion.info, picture_url=suggestion.payload.get('picture_url', ''))


@transaction.atomic
def decide(suggestion, verdict, rating=None):
    """verdict 'up' (Artist/Venue: braucht Rating 1–10; legt Artist, Venue bzw. Upcoming Event an) oder 'down'
    (Blacklist bzw. Konzert verworfen)."""
    if verdict == 'up':
        if suggestion.kind == Suggestion.Kind.EVENT:
            rating = None
        elif rating is None or not 1 <= rating <= 10:
            raise ValidationError(f'{suggestion.name}: Daumen hoch braucht ein Rating von 1 bis 10')
        _accept(suggestion, rating)
        suggestion.status, suggestion.rating = Suggestion.Status.ACCEPTED, rating
    elif verdict == 'down':
        suggestion.status = Suggestion.Status.REJECTED
    else:
        raise ValueError(f'Unbekannte Entscheidung: {verdict}')
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=['status', 'rating', 'decided_at'])
