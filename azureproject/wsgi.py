import os
import sys
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'azureproject.production')

# --- NEU: Wir schreiben direkt in den Error Stream ---
sys.stderr.write("\n\n🚑 STARTUP CHECK: Initializing...\n\n")

application = get_wsgi_application()

try:
    from homepage.models import ContactMessage
    count = ContactMessage.objects.count()
    sys.stderr.write(f"\n✅ DB SUCCESS: Count is {count}\n")
except Exception as e:
    sys.stderr.write(f"\n❌ DB CRITICAL FAILURE: {e}\n")
    # WIRF DEN FEHLER WEITER, damit Gunicorn crasht!
    raise e 
