import os
from django.core.wsgi import get_wsgi_application

# Wir setzen die Settings explizit, falls die Environment Variable fehlt
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'azureproject.production')

application = get_wsgi_application()
