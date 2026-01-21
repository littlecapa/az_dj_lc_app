#!/bin/bash
set -e

# Logging-Setup: Wir schreiben in eine Datei, aber WICHTIGES auch auf den Screen
LOGFILE="/tmp/startup.log"
echo "=== STARTUP SCRIPT STARTED at $(date) ===" | tee -a $LOGFILE

# 1. Sicherstellen, dass wir im richtigen Verzeichnis sind
cd /home/site/wwwroot

# 2. Migrationen ausführen
echo "🔄 Running migrations..." | tee -a $LOGFILE
python manage.py migrate --noinput || {
    echo "❌ CRITICAL: Migration failed!" | tee -a $LOGFILE
    # Wir lassen den Container trotzdem starten, damit man debuggen kann,
    # statt ihn in eine Crash-Loop zu schicken.
}

# 3. Static Files einsammeln
echo "📁 Collecting static files..." | tee -a $LOGFILE
python manage.py collectstatic --noinput --clear || {
    echo "⚠️ Collectstatic failed!" | tee -a $LOGFILE
}

# 4. Gunicorn Starten
echo "🚀 Starting Gunicorn..." | tee -a $LOGFILE

# WICHTIG:
# - Kein '>> logfile' am Ende! Azure braucht den Output direkt.
# - --chdir /home/site/wwwroot explizit setzen
# - exec sorgt dafür, dass Gunicorn PID 1 übernimmt (wichtig für Signale)

exec gunicorn --workers 2 --threads 4 --timeout 60 \
    --access-logfile '-' \
    --error-logfile '-' \
    --bind=0.0.0.0:8000 \
    --chdir=/home/site/wwwroot \
    azureproject.wsgi:application
