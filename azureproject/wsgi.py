import os
import sys
from django.core.wsgi import get_wsgi_application

# Settings setzen
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'azureproject.production')

application = get_wsgi_application()

# --- NEU: Startup Database Check ---
# Dieser Code läuft beim Starten von Gunicorn EINMAL.
try:
    print("🚑 STARTUP CHECK: Testing Database Connection...")
    
    # Modelle importieren (geht erst nach get_wsgi_application!)
    from homepage.models import ContactMessage
    
    # Versuchen, die Tabelle zu lesen
    count = ContactMessage.objects.count()
    
    print(f"✅ DB SUCCESS: Table 'ContactMessage' exists. Row count: {count}")

except Exception as e:
    # Fehler formatieren und laut ausgeben
    error_msg = f"❌ DB CRITICAL FAILURE: {str(e)}"
    print("\n" + "="*60)
    print(error_msg)
    print("="*60 + "\n")
    
    # Wir lassen die App NICHT abstürzen (kein exit), damit Sie den Log sehen können.
    # Aber wir loggen es als Error.
