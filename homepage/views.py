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
from azure.core.exceptions import HttpResponseError
from datetime import timedelta
import os, logging

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

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            # Daten speichern
            ContactMessage.objects.create(
                name=form.cleaned_data['name'],
                email=form.cleaned_data['email'],
                message=form.cleaned_data['message']
            )
            
            # Erfolgsmeldung
            messages.success(request, 'Vielen Dank! Ihre Nachricht wurde gespeichert.')
            return redirect('homepage:contact')
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
        error_message = "AZURE_LOG_WORKSPACE_ID not found."
    else:
        try:
            credential = DefaultAzureCredential()
            client = LogsQueryClient(credential)
            
            logger.info(f"🔍 Querying workspace {workspace_id[:8]}...")
            
            # DEBUG 1: Welche Tabellen gibt's? (letzte 24h)
            table_query = """
            search "*"
            | where TimeGenerated > ago(1d)
            | extend TableName = tostring(source_table)
            | summarize Count=count() by TableName
            | order by Count desc
            | take 10
            """
            
            table_response = client.query_workspace(
                workspace_id=workspace_id,
                query=table_query,
                timespan=timedelta(hours=24)
            )
            
            available_tables = []
            if table_response.tables:
                available_tables = [row[0] for row in table_response.tables[0].rows]
                logger.info(f"✅ Available tables (top 10): {available_tables}")
            
            # DEBUG 2: Haupt-Query (angepasst)
            query = """
            requests
            | where timestamp > ago(7d)
            | summarize requestCount=count() by url
            | order by requestCount desc
            | take 50
            """
            
            response = client.query_workspace(
                workspace_id=workspace_id,
                query=query,
                timespan=timedelta(days=7)
            )
            
            if response.tables and len(response.tables[0].rows) > 0:
                logger.info(f"✅ GOT {len(response.tables[0].rows)} URL stats!")
                for row in response.tables[0].rows:
                    url_stats.append({
                        'path': str(row[0])[:100],  # URL
                        'count': int(row[1])         # Count
                    })
                total_requests = sum(item['count'] for item in url_stats)
            else:
                logger.warning("❌ No data in 'requests' table. Check tables above.")
                error_message = f"No requests data. Available tables: {available_tables[:3]}"
                
        except Exception as e:
            logger.error(f"❌ Azure Error: {type(e).__name__}: {str(e)}")
            error_message = f"Query failed: {type(e).__name__}"

    context = {
        'url_stats': url_stats,
        'total_requests': total_requests,
        'error': error_message
    }
    return render(request, 'homepage/dashboard.html', context)