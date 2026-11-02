"""Vorschläge (Suggestion): Anlegen durch Claude (MCP add_suggestions) und Entscheidung im Formular."""

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone

from .models import Artist, Category, Suggestion, Venue

MAX_PER_CALL = 5

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


def _accept(suggestion, rating):
    if suggestion.kind == Suggestion.Kind.ARTIST:
        if not Artist.objects.filter(name__iexact=suggestion.name).exists():
            Artist.objects.create(name=suggestion.name, rating=rating, category=suggestion.category,
                                  info=suggestion.info, song_url=suggestion.payload.get('song_url', ''))
    elif not Venue.objects.filter(name__iexact=suggestion.name).exists():
        Venue.objects.create(name=suggestion.name, rating=rating, country=suggestion.payload.get('country', ''),
                             info=suggestion.info, picture_url=suggestion.payload.get('picture_url', ''))


@transaction.atomic
def decide(suggestion, verdict, rating=None):
    """verdict 'up' (braucht Rating 1–10, legt Artist bzw. Venue an) oder 'down' (Blacklist)."""
    if verdict == 'up':
        if rating is None or not 1 <= rating <= 10:
            raise ValidationError(f'{suggestion.name}: Daumen hoch braucht ein Rating von 1 bis 10')
        _accept(suggestion, rating)
        suggestion.status, suggestion.rating = Suggestion.Status.ACCEPTED, rating
    elif verdict == 'down':
        suggestion.status = Suggestion.Status.REJECTED
    else:
        raise ValueError(f'Unbekannte Entscheidung: {verdict}')
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=['status', 'rating', 'decided_at'])
