# fintech/urls.py

from django.urls import path, include
from . import views

app_name = "fintech" # Namespace für URL-Namen in diesem App-Teil

urlpatterns = [
    path('', views.fintech_index, name="fintech-index"),
    path('test_api/', views.test_api, name="test-api"),
    path('test_api/run/', views.test_api_run, name="test-api-run"),
    path('test_api/lookup/', views.test_api_lookup, name="test-api-lookup"),
    path('trigger/update-prices/', views.trigger_update_prices, name="trigger-update-prices"),
    path('trigger/cleanup/', views.trigger_cleanup, name="trigger-cleanup"),
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
    path("news/", views.news, name="news"),
]