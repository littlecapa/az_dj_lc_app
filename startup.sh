#!/bin/bash

# Exit on any error
set -e

echo "=== Starting Django Application ==="

# Run database migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Start Gunicorn
echo "Starting Gunicorn..."
gunicorn --workers 2 --threads 4 --timeout 60 \
    --access-logfile '-' --error-logfile '-' \
    --bind=0.0.0.0:8000 \
    --chdir=/home/site/wwwroot \
    azureproject.wsgi:application