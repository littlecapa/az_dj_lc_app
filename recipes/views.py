import csv
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, permissions
from rest_framework.decorators import action

from .models import Rezept
from .serializers import RezeptSerializer

logger = logging.getLogger(__name__)


class RezeptViewSet(viewsets.ModelViewSet):
    """CRUD + CSV-Export für Rezepte des eingeloggten Users."""

    serializer_class   = RezeptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Rezept.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
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


@login_required
def index(request):
    """Liefert die Rezepte-App (Under Construction bis React-Frontend fertig ist)."""
    return render(request, 'recipes/index.html')
