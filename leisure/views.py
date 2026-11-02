import datetime

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import EventVote, Suggestion
from .suggestions import decide

VOTER_SESSION_KEY = 'leisure_voter_name'

PAGES = {
    Suggestion.Kind.ARTIST: {'title': 'Neue Artists', 'label': 'Artist', 'url': 'leisure:new-artists'},
    Suggestion.Kind.VENUE: {'title': 'Neue Venues', 'label': 'Venue', 'url': 'leisure:new-venues'},
    Suggestion.Kind.EVENT: {'title': 'Neue Konzerte', 'label': 'Upcoming Event', 'url': 'leisure:new-events'},
}


def _with_event_data(suggestions):
    """Konzert-Vorschläge nach Datum sortiert, mit event_date und tally (Anzahl je Stimme aus den prefetchten votes)."""
    result = sorted(suggestions, key=lambda s: s.payload.get('date', ''))
    for suggestion in result:
        suggestion.event_date = datetime.date.fromisoformat(suggestion.payload['date'])
        votes = list(suggestion.votes.all())
        suggestion.tally = {v: sum(1 for x in votes if x.vote == v) for v in EventVote.Vote.values}
    return result


def _review(request, kind):
    """Vorschläge einer Art bewerten: Daumen hoch (+ Rating) → Artist, Venue bzw. Upcoming Event,
    Daumen runter → Blacklist bzw. verworfen."""
    page = PAGES[kind]
    pending = Suggestion.objects.filter(kind=kind, status=Suggestion.Status.PENDING).select_related('category')
    if request.method == 'POST':
        accepted, rejected, errors = [], [], []
        for suggestion in pending:
            verdict = request.POST.get(f'verdict_{suggestion.pk}')
            if verdict not in ('up', 'down'):
                continue
            raw_rating = request.POST.get(f'rating_{suggestion.pk}')
            try:
                decide(suggestion, verdict, int(raw_rating) if raw_rating else None)
            except ValidationError as exc:
                errors.extend(exc.messages)
                continue
            (accepted if verdict == 'up' else rejected).append(suggestion.name)
        if accepted:
            messages.success(request, f'Als {page["label"]} übernommen: {", ".join(accepted)}')
        if rejected:
            prefix = 'Verworfen' if kind == Suggestion.Kind.EVENT else 'Auf die Blacklist'
            messages.info(request, f'{prefix}: {", ".join(rejected)}')
        for error in errors:
            messages.error(request, error)
        return redirect(page['url'])

    is_event = kind == Suggestion.Kind.EVENT
    if is_event:  # Konzerte nach Datum, mit Stimmen der Freunde
        pending = _with_event_data(pending.prefetch_related('votes'))
    decided = Suggestion.objects.filter(kind=kind).exclude(status=Suggestion.Status.PENDING)
    return render(request, 'leisure/new_suggestions.html', {
        'page': page, 'is_venue': kind == Suggestion.Kind.VENUE, 'is_event': is_event, 'pending': pending,
        'decided': decided.order_by('-decided_at')[:10], 'ratings': range(10, 0, -1)})


@staff_member_required
def new_artists(request):
    return _review(request, Suggestion.Kind.ARTIST)


@staff_member_required
def new_venues(request):
    return _review(request, Suggestion.Kind.VENUE)


@staff_member_required
def new_events(request):
    return _review(request, Suggestion.Kind.EVENT)


def _save_votes(name, concerts, data):
    """Speichert die Stimmen eines Namens; leere Stimme + leerer Kommentar löscht eine vorhandene Stimme."""
    for concert in concerts:
        vote = data.get(f'vote_{concert.pk}', '')
        vote = vote if vote in EventVote.Vote.values else ''
        comment = data.get(f'comment_{concert.pk}', '').strip()[:300]
        existing = next((v for v in concert.votes.all() if v.name.lower() == name.lower()), None)
        if not vote and not comment:
            if existing:
                existing.delete()
        elif existing:
            existing.name, existing.vote, existing.comment = name, vote, comment
            existing.save()
        else:
            EventVote.objects.create(suggestion=concert, name=name, vote=vote, comment=comment)


def event_voting(request):
    """Öffentliche Abstimmseite für Freunde (wie Doodle): Name oben, je Konzert 👍/😐/👎 und ein Kommentar.
    Gezeigt werden offene und übernommene Konzert-Vorschläge ab heute, verworfene nicht."""
    today = timezone.localdate().isoformat()
    concerts = [c for c in _with_event_data(
        Suggestion.objects.filter(kind=Suggestion.Kind.EVENT, status__in=[Suggestion.Status.PENDING,
                                                                          Suggestion.Status.ACCEPTED])
        .prefetch_related('votes')) if c.payload['date'] >= today]
    if request.method == 'POST':
        name = ' '.join(request.POST.get('name', '').split())[:50]
        if not name:
            messages.error(request, 'Bitte oben deinen Namen eintragen.')
            return redirect('leisure:event-voting')
        request.session[VOTER_SESSION_KEY] = name
        if request.POST.get('action') == 'save':
            _save_votes(name, concerts, request.POST)
            messages.success(request, f'Danke, {name}! Deine Stimmen sind gespeichert.')
        return redirect('leisure:event-voting')

    name = request.session.get(VOTER_SESSION_KEY, '')
    for concert in concerts:
        concert.mine = next((v for v in concert.votes.all() if name and v.name.lower() == name.lower()), None)
        concert.others = [v for v in concert.votes.all() if v is not concert.mine]
    return render(request, 'leisure/event_voting.html', {
        'name': name, 'concerts': concerts, 'choices': EventVote.Vote.choices})
