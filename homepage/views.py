from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import ContactForm
from .chess_captcha import fen_to_board_rows, get_random_position, is_captcha_answer_correct, CAPTCHA_QUESTION
from .models import ContactMessage, BlogPost, HistChessMagazine, QuickLink, ChessPosition, ScbbCheck
from django.contrib.auth.decorators import user_passes_test
from django.views.generic import ListView, DetailView
from django.http import JsonResponse, HttpResponseNotAllowed
from django.template.loader import render_to_string
from azure.monitor.query import LogsQueryClient
from azure.identity import DefaultAzureCredential
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from core.jira_client import JiraClient, JiraApiError
import os, logging, time
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CHESS_MAG_CHECK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
# Seiten mit mindestens so viel sichtbarem Text gelten als "echter Inhalt" —
# ein enthaltenes "Fehler"/"Error" wird dann nicht mehr als Abbruchgrund gewertet.
SHORT_PAGE_TEXT_THRESHOLD = 500

class blog(ListView):
    model = BlogPost
    template_name = 'homepage/blog_list.html'
    context_object_name = 'posts'
    paginate_by = 10 

    def get_queryset(self):
        return BlogPost.objects.filter(is_active=True).order_by('-date')

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        context = self.get_context_data()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            html = render_to_string('homepage/post_list.html', context, request=request)
            return JsonResponse({
                'html': html,
                'has_next': context['page_obj'].has_next()
            })
        
        return super().render_to_response(context)

class BlogDetailView(DetailView):
    model = BlogPost
    # We do NOT set template_name here because it is dynamic
    context_object_name = 'post'

    def get_template_names(self):
        """
        Returns the template path based on the slug.
        Example: If slug is 'chess-championship', 
        it looks for 'homepage/blog/chess-championship.html'
        """
        slug = self.object.slug
        return [f'homepage/blog/{slug}.html']

def my_chess_club(request):
    return render(request, 'homepage/my_chess_club.html')

@never_cache
def historical_chess_mags(request):
    # Nur aktive Magazine holen
    active_mags = HistChessMagazine.objects.filter(is_active=True)

    # Gruppierung für das Template vorbereiten
    context = {
        'german_mags': active_mags.filter(language='German'),
        'english_mags': active_mags.filter(language='English'),
        'spanish_mags': active_mags.filter(language='Spanish'),
        'other_mags': active_mags.filter(language='Other'),
        'check_result': request.session.pop('chess_mag_check_result', None),
    }
    return render(request, 'homepage/historical-chess-mags.html', context)


@never_cache
@login_required
def check_historical_chess_mags(request):
    """
    Prüft alle aktiven HistChessMagazine-Links (ruft die Seite auf). Bei HTTP
    4xx (außer 403, siehe unten) oder wenn eine KURZE Seite (< SHORT_PAGE_TEXT_
    THRESHOLD Zeichen sichtbarer Text) 'Fehler'/'Error' enthält: is_active=False
    setzen und ein Jira-Bug-Ticket anlegen.

    HTTP 403 wird nicht als Fehler gewertet (Bot-/WAF-Schutz-Fehlalarme),
    sondern nur als "unclear" gemeldet. Umfangreiche Seiten mit viel echtem
    Inhalt lösen auch bei enthaltenem 'Fehler'/'Error' keinen Abbruch aus
    (z.B. JS-Apps, die eine ungenutzte Fehler-Vorlage mitliefern).
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    # TEMPORÄR: setzt vor jedem Check alle Magazine (auch zuvor deaktivierte)
    # wieder auf is_active=True, damit vorherige Fehlalarme nicht manuell im
    # Admin zurückgesetzt werden müssen. Wieder entfernen, sobald die
    # Prüf-Logik sich als zuverlässig genug erwiesen hat.
    HistChessMagazine.objects.update(is_active=True)

    checked = 0
    deactivated = []
    unclear = []

    for mag in HistChessMagazine.objects.filter(is_active=True):
        checked += 1
        try:
            response = requests.get(
                mag.link, headers=CHESS_MAG_CHECK_HEADERS, timeout=15, allow_redirects=True,
            )
        except requests.RequestException as exc:
            logger.warning(f"Chess-Mag-Check: {mag.name} ({mag.link}) nicht erreichbar: {exc}")
            unclear.append({"name": mag.name, "link": mag.link, "error": str(exc)})
            continue

        if response.status_code == 403:
            # Viele Seiten (Bot-/WAF-Schutz, z.B. Cloudflare) blocken Requests ohne
            # echten Browser mit 403, obwohl der Link für Menschen funktioniert.
            # Nicht deaktivieren, nur zur manuellen Prüfung melden.
            logger.info(f"Chess-Mag-Check: {mag.name} ({mag.link}) — HTTP 403 (evtl. Bot-Schutz), nicht deaktiviert")
            unclear.append({"name": mag.name, "link": mag.link, "error": "HTTP 403 (evtl. Bot-Schutz)"})
            continue

        reason = None
        if 400 <= response.status_code < 500:
            reason = f"HTTP {response.status_code}"
        else:
            # Nur sichtbaren Text prüfen, nicht den kompletten HTML/JS-Payload —
            # viele Seiten (React/Angular-Apps) betten Wörter wie "Error" in ihre
            # JS-Konfiguration/Übersetzungstabellen ein, ohne dass ein Fehler vorliegt.
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            visible_text = " ".join(soup.get_text().split())

            # Plausi: echte Fehlerseiten ("404 – Seite nicht gefunden") sind fast
            # immer kurz. Enthält eine umfangreiche Seite mit viel echtem Inhalt
            # das Wort "Fehler"/"Error" (z.B. eine mitgelieferte, aber ungenutzte
            # Fehler-Vorlage einer JS-App), ist das kein verlässliches Signal mehr.
            if len(visible_text) < SHORT_PAGE_TEXT_THRESHOLD and (
                "Fehler" in visible_text or "Error" in visible_text
            ):
                reason = (
                    f"Kurze Seite ({len(visible_text)} Zeichen sichtbarer Text) "
                    f"enthält 'Fehler'/'Error'"
                )

        if not reason:
            continue

        mag.is_active = False
        mag.save(update_fields=["is_active"])
        deactivated.append({"name": mag.name, "link": mag.link, "reason": reason})
        logger.info(f"Chess-Mag deaktiviert: {mag.name} ({mag.link}) — {reason}")

        try:
            JiraClient().create_issue(
                summary=f"Historical Chess Magazine Link tot: {mag.name}",
                description=(
                    f"Der Link eines Historical Chess Magazine ist nicht mehr aktuell:\n\n"
                    f"Name: {mag.name}\n"
                    f"Sprache: {mag.language}\n"
                    f"Link: {mag.link}\n"
                    f"Grund: {reason}\n"
                    f"HTTP-Status: {response.status_code}\n"
                    f"Zeitpunkt: {timezone.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
                    f"is_active wurde automatisch auf False gesetzt (Magazin ist damit "
                    f"von /historical-chess-mags/ verschwunden). Nach Prüfung/Korrektur im "
                    f"Django-Admin (Historical Chess Magazine → {mag.name}) wieder aktivieren."
                ),
                issue_type="Bug",
            )
        except JiraApiError as exc:
            logger.error(f"Jira-Ticket für {mag.name} konnte nicht angelegt werden: {exc}")

    request.session["chess_mag_check_result"] = {
        "checked": checked,
        "deactivated": deactivated,
        "unclear": unclear,
    }
    return redirect("homepage:historical-chess-mags")

def index(request):
    return render(request, 'homepage/index.html')


def links_page(request):
    # Links gruppiert nach Kategorie, sortiert nach prio + name
    links_qs = QuickLink.objects.filter(is_active=True).order_by('prio', 'name')
    categories = QuickLink.Category.choices  # feste Reihenfolge
    link_groups = [
        (label, [l for l in links_qs if l.category == value])
        for value, label in categories
        if any(l.category == value for l in links_qs)
    ]
    return render(request, 'homepage/links.html', {'link_groups': link_groups})

HARD_LIMIT = 20
SOFT_LIMIT = 10

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)

        # Captcha-Stellung stammt aus der Session (beim letzten Seitenaufruf gesetzt) —
        # nicht aus einem Hidden-Field im Request, sonst könnte ein Bot per manipuliertem
        # Feld immer dieselbe ihm bekannte Stellung "erzwingen" statt der tatsächlich
        # angezeigten.
        captcha_fen = request.session.get('captcha_fen')
        position = ChessPosition.objects.filter(pk=captcha_fen).first() if captcha_fen else None

        if form.is_valid():
            if position is None or not is_captcha_answer_correct(position, form.cleaned_data['captcha_answer']):
                form.add_error('captcha_answer', 'Falsche Antwort — bitte den besten Zug für Weiß angeben.')

        if not form.errors:
            email = form.cleaned_data['email']
            name = form.cleaned_data.get('name', '')
            message = form.cleaned_data.get('message', '')

            # --- Prüfung 3: Blacklist ---
            if ContactMessage.objects.filter(email=email, black_listed=True).exists():
                messages.error(request, "Sorry, you are on the Blacklist.")
                return redirect('homepage:contact')

            # --- Tagesfilter ---
            today = timezone.now().date()
            todays_messages = ContactMessage.objects.filter(
                created_at__date=today
            ).count()

            # --- Prüfung 2: Hard-Limit ---
            if todays_messages >= HARD_LIMIT:
                messages.error(request, "Daily message limit reached. Please try again tomorrow.")
                return redirect('homepage:contact')

            # --- Prüfung 1: Soft-Limit mit Pause ---
            if todays_messages > SOFT_LIMIT:
                delay = todays_messages * 2
                time.sleep(delay)

            # --- Speichern ---
            ContactMessage.objects.create(
                name=name,
                email=email,
                message=message
            )

            messages.success(request, f'Thank you very much! Your message has been saved. {todays_messages}')
            return redirect('homepage:contact')

        messages.error(request, 'Bitte korrigieren Sie die markierten Felder.')
    else:
        form = ContactForm()

    # Für jeden Seitenaufruf (auch nach fehlgeschlagenem Captcha) neu zufällig wählen
    # und in der Session merken, damit der nächste POST dieselbe Stellung prüft.
    position = get_random_position()
    request.session['captcha_fen'] = position.fen

    return render(request, 'homepage/contact.html', {
        'form': form,
        'board_rows': fen_to_board_rows(position.fen),
        'captcha_question': CAPTCHA_QUESTION,
    })

# Prüffunktion: Ist der User ein Admin?
def is_admin(user):
    return user.is_authenticated and user.is_superuser

@user_passes_test(is_admin)
def monitoring_view(request):
    # Zähle alle ungelesenen Nachrichten
    # Annahme: Ihr Model hat ein BooleanField 'is_read' oder ähnlich.
    # Falls nicht, müssen wir das anpassen (z.B. status='new').
    unread_count = ContactMessage.objects.filter(is_read=False).count()

    context = {
        'unread_count': unread_count,
    }
    return render(request, 'homepage/monitoring.html', context)

@user_passes_test(lambda u: u.is_superuser)
def dashboard_view(request):
    logger.info("DASHBOARD VIEW ENTERED")
    
    workspace_id = os.environ.get('AZURE_LOG_WORKSPACE_ID')
    url_stats = []
    total_requests = 0
    error_message = None

    if not workspace_id:
        error_message = "AZURE_LOG_WORKSPACE_ID not found in App Settings."
        logger.error(error_message)
    else:
        try:
            credential = DefaultAzureCredential()
            client = LogsQueryClient(credential)
            
            logger.info(f"🔍 Querying workspace {workspace_id[:8]}...")
            
            # Test 1: AppRequests (häufigste Tabelle)
            app_req_query = """
            AppRequests
            | where TimeGenerated > ago(7d)
            | summarize requestCount=count() by Url
            | order by requestCount desc
            | take 50
            """
            
            response = client.query_workspace(
                workspace_id=workspace_id,
                query=app_req_query,
                timespan=timedelta(days=7)
            )
            
            if response.tables and len(response.tables[0].rows) > 0:
                logger.info(f"✅ AppRequests: {len(response.tables[0].rows)} URLs gefunden!")
                for row in response.tables[0].rows:
                    url_stats.append({
                        'path': str(row[0])[:100] if row[0] else 'unknown',
                        'count': int(row[1])
                    })
                total_requests = sum(item['count'] for item in url_stats)
                
            else:
                # Test 2: requests (klassisch)
                logger.info("AppRequests leer → Teste 'requests'...")
                req_query = """
                requests
                | where timestamp > ago(7d)
                | summarize requestCount=count() by url
                | order by requestCount desc
                | take 50
                """
                
                response = client.query_workspace(
                    workspace_id=workspace_id,
                    query=req_query,
                    timespan=timedelta(days=7)
                )
                
                if response.tables and len(response.tables[0].rows) > 0:
                    logger.info(f"✅ requests: {len(response.tables[0].rows)} URLs gefunden!")
                    for row in response.tables[0].rows:
                        url_stats.append({
                            'path': str(row[0])[:100] if row[0] else 'unknown',
                            'count': int(row[1])
                        })
                    total_requests = sum(item['count'] for item in url_stats)
                else:
                    logger.warning("❌ Keine Request-Daten gefunden")
                    error_message = "Keine Web-Request-Daten in den letzten 7 Tagen."
            
        except Exception as e:
            logger.error(f"❌ Azure Error: {type(e).__name__}: {str(e)}")
            error_message = f"Query fehlgeschlagen: {type(e).__name__}"

    url_stats = [stat for stat in url_stats 
             if not stat['path'].endswith(('.php', 'robots.txt', 'api', 'api/', 'ectoplasm')) 
             and stat['count'] > 10]
    
    context = {
        'url_stats': url_stats,
        'total_requests': total_requests,
        'error': error_message
    }
    return render(request, 'homepage/dashboard.html', context)

@login_required
def api_overview(request):
    """API-Übersicht — alle Endpoints mit Beschreibung. Login erforderlich."""
    endpoints = [
        {
            "group": "Fintech – Portfolio (Read)",
            "color": "primary",
            "items": [
                {
                    "method": "GET",
                    "path": "/fintech/api/portfolio",
                    "auth": "Key / Session",
                    "desc": "Alle Positionen mit aktuellem Wert, Einstandspreis, absolutem und prozentualem P&L sowie Tages-Delta (delta_perc_1d). Enthält eine Gesamt-Summary.",
                },
                {
                    "method": "GET",
                    "path": "/fintech/api/watchlist",
                    "auth": "Key / Session",
                    "desc": "Alle Watchlist-Einträge sortiert nach Performance seit Aufnahme. Felder: watchlist, isin, name, current_price, price_at_add, delta_perc_since_add, source, notes.",
                },
                {
                    "method": "GET",
                    "path": "/fintech/api/assets/{isin}/history?days=30",
                    "auth": "Key / Session",
                    "desc": "Gespeicherte Kurshistorie für eine ISIN. Parameter: days (1–365, Standard 30). Gibt first_price, last_price, delta_perc sowie die vollständige history-Liste zurück.",
                },
                {
                    "method": "GET",
                    "path": "/fintech/api/securities/{isin}/price?type=STOCK",
                    "auth": "Key / Session",
                    "desc": "Aktuellen Kurs live abrufen (Comdirect + Yahoo Finance, Tiebreaker AlleAktien). type: STOCK | ETF | ETC | FOND | CRYPTO | DERIVATIVE.",
                },
            ],
        },
        {
            "group": "Fintech – Portfolio (Legacy)",
            "color": "secondary",
            "items": [
                {
                    "method": "GET",
                    "path": "/fintech/export",
                    "auth": "Key / Session",
                    "desc": "Portfolio als HTML-Seite mit eingebettetem JSON (Legacy-Endpoint). Für maschinenlesbare Daten /fintech/api/portfolio bevorzugen.",
                },
                {
                    "method": "GET",
                    "path": "/fintech/export_watchlist",
                    "auth": "Key / Session",
                    "desc": "Watchlist als HTML-Seite mit eingebettetem JSON (Legacy-Endpoint). Für maschinenlesbare Daten /fintech/api/watchlist bevorzugen.",
                },
            ],
        },
        {
            "group": "Fintech – Watchlist (Write)",
            "color": "success",
            "items": [
                {
                    "method": "POST",
                    "path": "/fintech/api/watchlist/create",
                    "auth": "Key / Session",
                    "desc": 'Neue Watchlist anlegen oder bestehende zurückgeben. Body: {"name": "Tech Favoriten"}.',
                },
                {
                    "method": "POST",
                    "path": "/fintech/api/watchlist/{name}/entries",
                    "auth": "Key / Session",
                    "desc": 'Asset zu einer Watchlist hinzufügen. Legt Asset und Watchlist bei Bedarf an. Holt aktiv Kurs wenn keiner gecacht ist. Body: {"isin": "...", "asset_class": "STOCK", "source": "...", "notes": "..."}.',
                },
                {
                    "method": "DELETE",
                    "path": "/fintech/api/watchlist/{name}/entries/{isin}",
                    "auth": "Key / Session",
                    "desc": "Einzelnen Eintrag aus einer Watchlist entfernen. Das Asset selbst bleibt erhalten. Gibt entries_left zurück.",
                },
                {
                    "method": "DELETE",
                    "path": "/fintech/api/watchlist/{name}",
                    "auth": "Key / Session",
                    "desc": "Gesamte Watchlist inkl. aller Einträge löschen. Assets bleiben erhalten. Gibt entries_removed zurück.",
                },
            ],
        },
        {
            "group": "Fintech – Assets (Write)",
            "color": "success",
            "items": [
                {
                    "method": "POST",
                    "path": "/fintech/api/assets/{isin}/resolve-name",
                    "auth": "Key / Session",
                    "desc": 'Namen für eine ISIN bei Yahoo Finance nachschlagen und Asset aktualisieren. Überschreibt nur wenn name==isin oder {"force": true} übergeben wird.',
                },
                {
                    "method": "POST",
                    "path": "/fintech/api/assets/resolve-names",
                    "auth": "Key / Session",
                    "desc": 'Bulk: Namen für alle Assets auflösen wo name==isin. Mit {"force": true} werden alle Assets aktualisiert. 207 bei Teilfehlern.',
                },
            ],
        },
        {
            "group": "Fintech – Fund-Holdings (Read)",
            "color": "primary",
            "items": [
                {
                    "method": "GET",
                    "path": "/fintech/api/funds/{fund_isin}/holdings/top10",
                    "auth": "Key / Session",
                    "desc": "Top-10-Holdings eines Fonds/ETF inkl. Gewichtung (%), live per JustETF-Scraping. JustETF zeigt kostenlos nur die 10 größten Positionen.",
                },
            ],
        },
        {
            "group": "Fintech – Quick Links (Write)",
            "color": "success",
            "items": [
                {
                    "method": "POST",
                    "path": "/fintech/api/quicklinks/import",
                    "auth": "Key / Session",
                    "desc": 'Bulk-Import von Quick Links. Body: JSON-Array mit Objekten {name, url, category, prio, is_active}. Bestehende Links (gleicher Name + Kategorie) werden aktualisiert. Kategorien: Chess | Finance | AI | Video | News | Misc | Travel | Bonn.',
                },
            ],
        },
        {
            "group": "Fintech – Portfolio (Login)",
            "color": "success",
            "items": [
                {
                    "method": "GET",
                    "path": "/fintech/portfolio/",
                    "auth": "Login",
                    "desc": "Portfolio-Übersicht nach Kategorie (18 neue Kategorien). Toggle Gesamt/Tag-Performance, Sortierung per Klick. 4 Kacheln pro Reihe.",
                },
                {
                    "method": "GET",
                    "path": "/fintech/portfolio/{category}/",
                    "auth": "Login",
                    "desc": "Detailansicht einer Kategorie: alle Holdings mit Einstand, aktuellem Kurs, G/V, Tagesperformance. Toggle + Prev/Next-Navigation. Links zu TradingView / JustETF / onvista.",
                },
                {
                    "method": "GET",
                    "path": "/fintech/winner/",
                    "auth": "Login",
                    "desc": "Winners & Losers: 4 Spalten mit je Top-10 — bester/schlechtester Tag, beste/schlechteste Gesamtperformance. Inkl. Portfolio-Summary.",
                },
            ],
        },
        {
            "group": "Fintech – Watchlist (Login)",
            "color": "info",
            "items": [
                {
                    "method": "GET",
                    "path": "/fintech/watchlist-performance/",
                    "auth": "Login",
                    "desc": "Übersicht aller Watchlisten mit annualisierter Rendite p.a. (Annahme: 10.000 € pro Position). Sortiert nach bester Performance.",
                },
                {
                    "method": "GET",
                    "path": "/fintech/watchlist-performance/{name}/",
                    "auth": "Login",
                    "desc": "Drill-down einer Watchlist: alle Positionen mit Einstiegskurs, aktuellem Kurs, Haltedauer, hypothetischem Wert, einfacher und annualisierter Rendite.",
                },
            ],
        },
        {
            "group": "Homepage – Verwaltung",
            "color": "warning",
            "items": [
                {
                    "method": "GET/POST",
                    "path": "/fintech/import",
                    "auth": "Staff-Login",
                    "desc": "CSV-Import von Transaktionen (Portfolio-Positionen). Unterstützt Dry-Run.",
                },
                {
                    "method": "GET/POST",
                    "path": "/fintech/import_watchlist",
                    "auth": "Staff-Login",
                    "desc": "JSON-Import von Watchlist-Einträgen über ein Web-Formular.",
                },
                {
                    "method": "GET",
                    "path": "/api-overview/",
                    "auth": "Login",
                    "desc": "Diese Seite — Übersicht aller API-Endpoints.",
                },
            ],
        },
    ]
    return render(request, "homepage/api_overview.html", {"endpoints": endpoints})


# =====================================================================
# SCBB Monitoring (Erreichbarkeit https://scbb.de/)
# =====================================================================

SCBB_TARGET_URL = "https://scbb.de/"
SCBB_CHECK_TIMEOUT = 15
# Verhindert, dass viele schnell aufeinanderfolgende Aufrufe (Button-Doppelklick,
# Cron-Fehlkonfiguration) scbb.de mit Requests fluten oder die Tabelle vollmüllen.
SCBB_CHECK_MIN_INTERVAL = timedelta(seconds=5)


def perform_scbb_check():
    """Ruft SCBB_TARGET_URL auf, misst die Antwortzeit und speichert einen ScbbCheck-Datensatz."""
    start = time.monotonic()
    status_code = None
    error = ""
    try:
        response = requests.get(SCBB_TARGET_URL, headers=CHESS_MAG_CHECK_HEADERS, timeout=SCBB_CHECK_TIMEOUT)
        status_code = response.status_code
    except requests.RequestException as exc:
        error = str(exc)[:255]
        logger.warning(f"SCBB-Check: {SCBB_TARGET_URL} nicht erreichbar: {exc}")

    response_time_ms = round((time.monotonic() - start) * 1000)
    return ScbbCheck.objects.create(
        status_code=status_code,
        response_time_ms=response_time_ms,
        error=error,
    )


@csrf_exempt
def scbb_check_api(request):
    """
    REST-Endpoint, um einen SCBB-Check auszulösen. Bewusst ohne Auth
    (öffentlich erreichbar), z.B. für curl/Cron: POST /scbb/check/
    CSRF-exempt, damit auch externe curl/Cron-Aufrufe ohne Session-Cookie
    funktionieren.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    last_check = ScbbCheck.objects.order_by('-checked_at').first()
    if last_check and timezone.now() - last_check.checked_at < SCBB_CHECK_MIN_INTERVAL:
        check = last_check
        throttled = True
    else:
        check = perform_scbb_check()
        throttled = False

    return JsonResponse({
        'checked_at': check.checked_at.isoformat(),
        'status_code': check.status_code,
        'response_time_ms': check.response_time_ms,
        'error': check.error,
        'throttled': throttled,
    })


def scbb_monitor_view(request):
    """Öffentliche Monitoring-Seite für https://scbb.de/ — Button + Diagramme."""
    checks = ScbbCheck.objects.order_by('-checked_at')[:200]
    checks = list(reversed(checks))  # chronologisch für den Zeitverlauf

    status_counts = (
        ScbbCheck.objects.values('status_code')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    status_labels = [str(row['status_code']) if row['status_code'] is not None else 'Fehler' for row in status_counts]
    status_data = [row['count'] for row in status_counts]

    response_time_labels = [c.checked_at.strftime('%d.%m. %H:%M') for c in checks]
    response_time_data = [c.response_time_ms for c in checks]

    context = {
        'target_url': SCBB_TARGET_URL,
        'latest_check': checks[-1] if checks else None,
        'status_labels': status_labels,
        'status_data': status_data,
        'response_time_labels': response_time_labels,
        'response_time_data': response_time_data,
        'total_checks': ScbbCheck.objects.count(),
    }
    return render(request, 'homepage/scbb.html', context)
