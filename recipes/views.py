import csv
import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from rest_framework import viewsets, permissions
from rest_framework.decorators import action

from .models import Rezept
from .serializers import RezeptSerializer
from .services.importer import parse_excel, parse_csv, do_import

logger = logging.getLogger(__name__)


class ReadPublicWriteAuthenticated(permissions.BasePermission):
    """GET/HEAD/OPTIONS für alle; POST/PATCH/DELETE nur eingeloggt."""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)


class RezeptViewSet(viewsets.ModelViewSet):
    """CRUD + CSV-Export. Lesen öffentlich, Schreiben nur eingeloggt."""

    serializer_class   = RezeptSerializer
    permission_classes = [ReadPublicWriteAuthenticated]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            # Eingeloggter User sieht nur seine eigenen Rezepte
            return Rezept.objects.filter(user=self.request.user)
        # Öffentlich: alle Rezepte
        return Rezept.objects.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def export_csv(self, request):
        """GET /rezepte/api/rezepte/export_csv/"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="meine-rezepte.csv"'
        response.write('﻿')   # UTF-8 BOM für Excel
        writer = csv.writer(response)
        writer.writerow(['name', 'kategorie', 'aufwand', 'quelle', 'zutaten',
                         'zeit', 'saison', 'notiz', 'link', 'liebling'])
        for r in self.get_queryset():
            writer.writerow([
                r.name, r.kategorie, r.aufwand, r.quelle, r.zutaten,
                r.zeit or '', r.saison, r.notiz, r.link,
                'ja' if r.liebling else 'nein',
            ])
        return response


def index(request):
    """Rezepte-Hauptseite — öffentlich lesbar."""
    return render(request, 'recipes/app.html')


@login_required
def import_view(request):
    """Upload Excel/CSV → Vorschau → Import."""
    result = None
    rows   = None

    if request.method == 'POST':
        uploaded = request.FILES.get('rezept_file')
        dry_run  = request.POST.get('dry_run') == 'on'

        if not uploaded:
            messages.error(request, 'Bitte eine Datei auswählen.')
            return redirect('recipes:import')

        fname = uploaded.name.lower()
        try:
            if fname.endswith('.xlsx') or fname.endswith('.xls'):
                rows = parse_excel(uploaded)
            elif fname.endswith('.csv'):
                rows = parse_csv(uploaded)
            else:
                messages.error(request, 'Nur .xlsx und .csv Dateien werden unterstützt.')
                return redirect('recipes:import')
        except Exception as exc:
            messages.error(request, f'Fehler beim Lesen der Datei: {exc}')
            return redirect('recipes:import')

        result = do_import(rows, user=request.user, dry_run=dry_run)

    return render(request, 'recipes/import.html', {'result': result})
