"""Bordkasse & Einkaufsliste pro Törn.

Lesen ist öffentlich. Törn anlegen und alle Änderungen an Crew/Buchungen
erfordern Login; die Einkaufsliste darf jeder bearbeiten.
"""
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Buchung, BuchungRevision, BordkasseKonfig, CrewMember, ShoppingItem, Toern, toern_slugify
from .services import STANDARD_LIST, build_export, build_settlement, can_write, serialize_state

logger = logging.getLogger(__name__)


def _login_pflicht(request):
    """True, wenn laut Bordkasse_Konfig Login nötig ist und der Besucher nicht angemeldet ist."""
    return BordkasseKonfig.load().authentifizierung_erforderlich and not request.user.is_authenticated


def zugang(view_func):
    """Alle Bordkassen-Seiten: bei aktiver Authentifizierungspflicht erst Login."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if _login_pflicht(request):
            return redirect_to_login(request.get_full_path())
        return view_func(request, *args, **kwargs)
    return wrapper


# ------------------------------------------------------------------ Seiten

@zugang
def toern_list(request):
    """/bordkasse/ — alle Törns, Anlegen nur eingeloggt."""
    if request.method == 'POST':
        if not can_write(request.user):
            return redirect_to_login(request.get_full_path())
        name = ' '.join(request.POST.get('name', '').split())[:60]
        slug = toern_slugify(name)
        if not name or not slug:
            messages.error(request, 'Bitte einen Namen mit Buchstaben oder Ziffern angeben.')
            return redirect('bordkasse:index')
        existing = Toern.objects.filter(Q(name__iexact=name) | Q(slug=slug)).first()
        if existing:
            messages.info(request, f'Den Törn „{existing.name}“ gibt es schon.')
            return redirect('bordkasse:detail', slug=existing.slug)
        toern = Toern.objects.create(name=name, slug=slug, created_by=request.user)
        return redirect('bordkasse:detail', slug=toern.slug)

    toerns = Toern.objects.annotate(
        crew_count=Count('crew', distinct=True),
        tx_count=Count('buchungen', filter=Q(buchungen__deleted=False), distinct=True),
        open_count=Count('einkaufsliste', filter=Q(einkaufsliste__done=False), distinct=True),
    )
    return render(request, 'bordkasse/toern_list.html', {
        'toerns': toerns,
        'can_write': can_write(request.user),
    })


@zugang
@ensure_csrf_cookie
def toern_detail(request, slug):
    """/bordkasse/<slug>/ — eigentliche Bordkasse; Daten kommen per JSON-API."""
    toern = get_object_or_404(Toern, slug=slug)
    return render(request, 'bordkasse/toern_detail.html', {
        'toern': toern,
        'can_write': can_write(request.user),
        'initial_state': serialize_state(toern, request.user),
        'standard_list': STANDARD_LIST,
    })


@zugang
@require_GET
def abrechnung(request, slug):
    """/bordkasse/<slug>/abrechnung/ — Endabrechnung mit nachvollziehbarem Rechenweg (öffentlich)."""
    toern = get_object_or_404(Toern, slug=slug)
    return render(request, 'bordkasse/abrechnung.html', {
        'toern': toern,
        'a': build_settlement(toern),
        'stand': timezone.now(),
    })


@zugang
@require_GET
def export_xlsx(request, slug):
    toern = get_object_or_404(Toern, slug=slug)
    fname = f'Bordkasse_{toern.slug}_{date.today().isoformat()}.xlsx'
    response = HttpResponse(
        build_export(toern),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    return response


# ------------------------------------------------------------------ JSON-API

class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def api(login=False):
    """POST-API-View: lädt den Törn, parst JSON, prüft Login, liefert den neuen Gesamtzustand."""
    def deco(fn):
        @wraps(fn)
        @require_POST
        def wrapper(request, slug, *args, **kwargs):
            if _login_pflicht(request):
                return JsonResponse({'error': 'Bitte anmelden.'}, status=403)
            toern = get_object_or_404(Toern, slug=slug)
            if login and not can_write(request.user):
                return JsonResponse({'error': 'Bitte anmelden, um die Bordkasse zu ändern.'}, status=403)
            try:
                data = json.loads(request.body or b'{}')
                if not isinstance(data, dict):
                    raise ValueError
            except ValueError:
                return JsonResponse({'error': 'Ungültige Anfrage.'}, status=400)
            try:
                with transaction.atomic():
                    fn(request, toern, data, *args, **kwargs)
                    toern.touch()
            except ApiError as e:
                return JsonResponse({'error': str(e)}, status=e.status)
            return JsonResponse(serialize_state(toern, request.user))
        return wrapper
    return deco


@require_GET
def api_state(request, slug):
    if _login_pflicht(request):
        return JsonResponse({'error': 'Bitte anmelden.'}, status=403)
    toern = get_object_or_404(Toern, slug=slug)
    return JsonResponse(serialize_state(toern, request.user))


def _clean(data, key, max_len):
    return ' '.join(str(data.get(key) or '').split())[:max_len]


def _amount(data):
    try:
        value = Decimal(str(data.get('amount', '')).replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ApiError('Bitte einen gültigen Betrag eingeben.')
    if value <= 0 or value >= Decimal('100000000'):
        raise ApiError('Bitte einen gültigen Betrag eingeben.')
    return value


def _apply_buchung_fields(toern, buchung, data):
    kind = data.get('kind')
    if kind not in (Buchung.AUSGABE, Buchung.EINZAHLUNG):
        raise ApiError('Unbekannte Buchungsart.')
    person_id = data.get('person_id')
    person = None
    if person_id not in (None, '', 'kasse'):
        person = CrewMember.objects.filter(toern=toern, pk=person_id).first()
        if person is None:
            raise ApiError('Unbekanntes Crew-Mitglied.')
    if kind == Buchung.EINZAHLUNG and person is None:
        raise ApiError('Eine Einzahlung braucht eine Person.')

    buchung.kind = kind
    buchung.person = person
    buchung.amount = _amount(data)
    buchung.note = _clean(data, 'note', 80)
    if kind == Buchung.EINZAHLUNG:
        buchung.method = ''
    elif person is None:
        buchung.method = Buchung.BAR  # Ausgaben aus der Bordkasse sind immer Bargeld
    else:
        buchung.method = Buchung.BAR if data.get('method') == Buchung.BAR else Buchung.KARTE


@api(login=True)
def api_crew_add(request, toern, data):
    name = _clean(data, 'name', 40)
    if not name:
        raise ApiError('Bitte einen Namen eingeben.')
    if toern.crew.filter(name__iexact=name).exists():
        raise ApiError(f'„{name}“ ist schon in der Crew.')
    CrewMember.objects.create(toern=toern, name=name)


@api(login=True)
def api_crew_rename(request, toern, data, pk):
    member = get_object_or_404(CrewMember, toern=toern, pk=pk)
    name = _clean(data, 'name', 40)
    if not name:
        raise ApiError('Bitte einen Namen eingeben.')
    if toern.crew.filter(name__iexact=name).exclude(pk=pk).exists():
        raise ApiError(f'„{name}“ ist schon in der Crew.')
    # Buchungen/Revisionen verweisen per FK auf die Person — die Umbenennung
    # gilt damit automatisch für Saldo, Buchungsliste und Historie.
    member.name = name
    try:
        member.save(update_fields=['name'])
    except IntegrityError:
        raise ApiError(f'„{name}“ ist schon in der Crew.')


@api(login=True)
def api_tx_add(request, toern, data):
    buchung = Buchung(toern=toern, created_by=request.user)
    _apply_buchung_fields(toern, buchung, data)
    buchung.save()


@api(login=True)
def api_tx_edit(request, toern, data, pk):
    buchung = get_object_or_404(Buchung.objects.select_for_update(), toern=toern, pk=pk)
    if buchung.deleted:
        raise ApiError('Gelöschte Buchungen können nicht bearbeitet werden.')
    before = BuchungRevision(
        buchung=buchung, changed_by=request.user, kind=buchung.kind, person_id=buchung.person_id,
        amount=buchung.amount, method=buchung.method, note=buchung.note,
    )
    _apply_buchung_fields(toern, buchung, data)
    changed = (before.kind, before.person_id, before.amount, before.method, before.note) != \
              (buchung.kind, buchung.person_id, buchung.amount, buchung.method, buchung.note)
    if changed:
        before.save()
        buchung.updated_at = timezone.now()
        buchung.save()


@api(login=True)
def api_tx_delete(request, toern, data, pk):
    buchung = get_object_or_404(Buchung, toern=toern, pk=pk)
    if not buchung.deleted:
        buchung.deleted = True
        buchung.deleted_at = timezone.now()
        buchung.deleted_by = request.user
        buchung.save(update_fields=['deleted', 'deleted_at', 'deleted_by'])


@api()
def api_shop_add(request, toern, data):
    text = _clean(data, 'text', 80)
    if not text:
        raise ApiError('Bitte einen Artikel eingeben.')
    if toern.einkaufsliste.filter(done=False, text__iexact=text).exists():
        raise ApiError(f'„{text}“ steht schon auf der Liste.', status=409)
    ShoppingItem.objects.create(toern=toern, text=text)


@api()
def api_shop_update(request, toern, data, pk):
    item = get_object_or_404(ShoppingItem, toern=toern, pk=pk)
    fields = []
    if 'done' in data:
        item.done = bool(data['done'])
        fields.append('done')
    if 'qty' in data:
        item.qty = _clean(data, 'qty', 24)
        fields.append('qty')
    if 'info' in data:
        item.info = _clean(data, 'info', 60)
        fields.append('info')
    if fields:
        item.save(update_fields=fields)


@api()
def api_shop_delete(request, toern, data, pk):
    ShoppingItem.objects.filter(toern=toern, pk=pk).delete()
