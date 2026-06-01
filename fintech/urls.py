# fintech/urls.py

from django.urls import path, include
from . import views

app_name = "fintech" # Namespace für URL-Namen in diesem App-Teil

urlpatterns = [
    path('api/', include('fintech.apis.urls')),
    path("export", views.portfolio_export, name="portfolio-export"),
    path("export_watchlist", views.watchlist_export, name="watchlist-export"),
    path("import", views.portfolio_import, name="portfolio-import"),
    path("import_watchlist", views.watchlist_import, name="watchlist-import"),
    path("watchlist-performance/", views.watchlist_performance, name="watchlist-performance"),
    path("watchlist-performance/<str:watchlist_name>/", views.watchlist_detail, name="watchlist-detail"),
]