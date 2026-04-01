# fintech/urls.py

from django.urls import path, include
from . import views

app_name = "fintech" # Namespace für URL-Namen in diesem App-Teil

urlpatterns = [
    path('api/', include('fintech.apis.urls')),
    path("export", views.portfolio_export, name="portfolio-export"),
    path("import", views.portfolio_import, name="portfolio-import"),
]