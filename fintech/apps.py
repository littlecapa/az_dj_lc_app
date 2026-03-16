# fintech/apps.py
import os
import sys
from django.apps import AppConfig

class FintechConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fintech'

    def ready(self):
        # Verhindert, dass das Skript bei manage.py Befehlen (wie makemigrations) 
        # oder mehrfach durch den Auto-Reloader läuft.
        # In Produktion (Azure/gunicorn) oder im MAIN-Thread von runserver:
        
        is_manage_command = len(sys.argv) > 1 and sys.argv[1] in ['makemigrations', 'migrate', 'collectstatic']
        
        if not is_manage_command:
            # Für runserver (Dev): Nur im Hauptprozess ausführen
            # Für Azure (Prod): RUN_MAIN ist oft nicht gesetzt, wird aber nur einmal gestartet
            if os.environ.get('RUN_MAIN', None) == 'true' or not os.environ.get('DJANGO_DEVELOPMENT', False):
                try:
                    # Import hierhin verschieben, da Models vorher noch nicht bereit sind
                    from . import comdirect
                    comdirect.run_import()
                except Exception as e:
                    print(f"Fehler beim initialen Comdirect-Import: {e}")
