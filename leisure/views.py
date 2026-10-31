from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from .models import Suggestion
from .suggestions import decide


@staff_member_required
def new_artists(request):
    """Neue Artist-Vorschläge bewerten: Daumen hoch + Rating → Artist, Daumen runter → Blacklist."""
    pending = Suggestion.objects.filter(kind=Suggestion.Kind.ARTIST, status=Suggestion.Status.PENDING).select_related('category')
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
            messages.success(request, f'Als Artist übernommen: {", ".join(accepted)}')
        if rejected:
            messages.info(request, f'Auf die Blacklist: {", ".join(rejected)}')
        for error in errors:
            messages.error(request, error)
        return redirect('leisure:new-artists')

    decided = Suggestion.objects.filter(kind=Suggestion.Kind.ARTIST).exclude(status=Suggestion.Status.PENDING)
    return render(request, 'leisure/new_artists.html', {
        'pending': pending, 'decided': decided.order_by('-decided_at')[:10], 'ratings': range(10, 0, -1)})
