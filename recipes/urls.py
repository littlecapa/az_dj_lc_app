from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import RezeptViewSet, index, import_view

router = DefaultRouter()
router.register(r'rezepte', RezeptViewSet, basename='rezept')

app_name = 'recipes'

urlpatterns = [
    path('',        index,       name='index'),    # /rezepte/
    path('import/', import_view, name='import'),  # /rezepte/import/
    path('api/',    include(router.urls)),         # /rezepte/api/rezepte/
]

# Generierte API-Endpunkte:
#   GET  /POST          /rezepte/api/rezepte/
#   GET  /PATCH/DELETE  /rezepte/api/rezepte/{id}/
#   GET                 /rezepte/api/rezepte/export_csv/
