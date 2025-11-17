#!/bin/bash
set -e

echo "=== STARTUP SCRIPT STARTED ===" >> /tmp/startup.log 2>&1

echo "Running migrations..." >> /tmp/startup.log 2>&1
python manage.py migrate --noinput >> /tmp/startup.log 2>&1 || echo "MIGRATE FAILED" >> /tmp/startup.log 2>&1

echo "Collecting static files..." >> /tmp/startup.log 2>&1
python manage.py collectstatic --noinput --clear >> /tmp/startup.log 2>&1 || echo "COLLECTSTATIC FAILED" >> /tmp/startup.log 2>&1

echo "Starting Gunicorn..." >> /tmp/startup.log 2>&1
gunicorn --workers 2 --threads 4 --timeout 60 \
    --access-logfile '-' --error-logfile '-' \
    --bind=0.0.0.0:8000 \
    --chdir=/home/site/wwwroot \
    azureproject.wsgi:application >> /tmp/startup.log 2>&1