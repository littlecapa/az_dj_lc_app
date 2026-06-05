# fintech/urls.py

from django.urls import path, include
from . import views

app_name = "fintech" # Namespace für URL-Namen in diesem App-Teil

urlpatterns = [
    path('', views.fintech_index, name="fintech-index"),
    path('api/', include('fintech.apis.urls')),
    path("export", views.portfolio_export, name="portfolio-export"),
    path("export_watchlist", views.watchlist_export, name="watchlist-export"),
    path("import", views.portfolio_import, name="portfolio-import"),
    path("import_watchlist", views.watchlist_import, name="watchlist-import"),
    path("overall/", views.portfolio_overall, name="portfolio-overall"),
    path("portfolio/", views.portfolio_performance, name="portfolio-performance"),
    path("winner/", views.portfolio_winners, name="portfolio-winners"),
    path("portfolio/<slug:category_slug>/", views.portfolio_category_detail, name="portfolio-category-detail"),
    path("watchlist-performance/", views.watchlist_performance, name="watchlist-performance"),
    path("watchlist-performance/<str:watchlist_name>/", views.watchlist_detail, name="watchlist-detail"),
]