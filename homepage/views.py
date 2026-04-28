from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ContactForm
from .models import ContactMessage, BlogPost, HistChessMagazine
from django.contrib.auth.decorators import user_passes_test
from django.views.generic import ListView, DetailView
from django.http import JsonResponse
from django.template.loader import render_to_string 
from azure.monitor.query import LogsQueryClient
from azure.identity import DefaultAzureCredential
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
import os, logging, time

logger = logging.getLogger(__name__)

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

def historical_chess_mags(request):
    # Nur aktive Magazine holen
    active_mags = HistChessMagazine.objects.filter(is_active=True)

    # Gruppierung für das Template vorbereiten
    context = {
        'german_mags': active_mags.filter(language='German'),
        'english_mags': active_mags.filter(language='English'),
        'spanish_mags': active_mags.filter(language='Spanish'),
        'other_mags': active_mags.filter(language='Other'),
    }
    return render(request, 'homepage/historical-chess-mags.html', context)

def index(request):
    return render(request, 'homepage/index.html')

HARD_LIMIT = 20
SOFT_LIMIT = 10

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)

        if form.is_valid():
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

    return render(request, 'homepage/contact.html', {'form': form})

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