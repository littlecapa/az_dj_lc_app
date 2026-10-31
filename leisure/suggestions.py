"""Vorschläge (Suggestion): Anlegen durch Claude (MCP add_suggestions) und Entscheidung im Formular."""

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone

from .models import Artist, Category, Suggestion

MAX_PER_CALL = 5


def _skip_reason(name):
    if Artist.objects.filter(name__iexact=name).exists():
        return 'gibt es schon als Artist'
    existing = Suggestion.objects.filter(kind=Suggestion.Kind.ARTIST, name__iexact=name).first()
    if existing:
        return {Suggestion.Status.PENDING: 'ist schon vorgeschlagen und noch offen',
                Suggestion.Status.ACCEPTED: 'wurde schon übernommen',
                Suggestion.Status.REJECTED: 'wurde abgelehnt (Blacklist)'}[existing.status]
    return None


def add_artist_suggestions(items):
    """Legt bis zu MAX_PER_CALL Artist-Vorschläge an. Bekannte, offene oder abgelehnte Namen werden übersprungen."""
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
        reason = _skip_reason(name)
        category = categories.get((item.get('category') or '').strip().lower())
        song_url = (item.get('song_url') or '').strip()
        if not reason and category is None:
            reason = f'unbekannte Kategorie "{item.get("category")}", erlaubt: {", ".join(c.name for c in categories.values())}'
        if not reason and song_url:
            try:
                URLValidator()(song_url)
            except ValidationError:
                reason = f'song_url ist keine gültige URL: {song_url}'
        if reason:
            skipped.append({'name': name, 'reason': reason})
            continue
        Suggestion.objects.create(kind=Suggestion.Kind.ARTIST, name=name, category=category,
                                  info=(item.get('info') or '').strip(),
                                  payload={'song_url': song_url} if song_url else {})
        created.append(name)
    return {'created': created, 'skipped': skipped}


@transaction.atomic
def decide(suggestion, verdict, rating=None):
    """verdict 'up' (braucht Rating 1–10, legt den Artist an) oder 'down' (Blacklist)."""
    if verdict == 'up':
        if rating is None or not 1 <= rating <= 10:
            raise ValidationError(f'{suggestion.name}: Daumen hoch braucht ein Rating von 1 bis 10')
        if not Artist.objects.filter(name__iexact=suggestion.name).exists():
            Artist.objects.create(name=suggestion.name, rating=rating, category=suggestion.category,
                                  info=suggestion.info, song_url=suggestion.payload.get('song_url', ''))
        suggestion.status, suggestion.rating = Suggestion.Status.ACCEPTED, rating
    elif verdict == 'down':
        suggestion.status = Suggestion.Status.REJECTED
    else:
        raise ValueError(f'Unbekannte Entscheidung: {verdict}')
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=['status', 'rating', 'decided_at'])
