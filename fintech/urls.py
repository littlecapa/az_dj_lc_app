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
    path('trigger/update-etf-holdings/', views.trigger_update_etf_holdings, name="trigger-update-etf-holdings"),
    path('clean_up/', views.clean_up, name="clean-up"),
    path('backup/', views.backup_page, name="backup-page"),
    path('backup/download/', views.backup_download, name="backup-download"),
    path('trigger/refresh-week52/', views.trigger_refresh_week52, name="trigger-refresh-week52"),
    path('api/', include('fintech.apis.urls')),
    path("export", views.portfolio_export, name="portfolio-export"),
    path("export_watchlist", views.watchlist_export, name="watchlist-export"),
    path("import", views.portfolio_import, name="portfolio-import"),
    path("import_watchlist", views.watchlist_import, name="watchlist-import"),
    path("overall/", views.portfolio_overall, name="portfolio-overall"),
    path("overall-stocks/", views.portfolio_overall_stocks, name="portfolio-overall-stocks"),
    path("manual-fund-holdings/", views.manual_fund_holdings_edit, name="manual-fund-holdings"),
    path("manual-fund-holdings/<str:isin>/", views.manual_fund_holdings_edit, name="manual-fund-holdings-edit"),
    path("portfolio/", views.portfolio_performance, name="portfolio-performance"),
    path("winner/", views.portfolio_winners, name="portfolio-winners"),
    path("portfolio/<slug:category_slug>/", views.portfolio_category_detail, name="portfolio-category-detail"),
    path("watchlist-performance/", views.watchlist_performance, name="watchlist-performance"),
    path("watchlists_all/", views.watchlists_all, name="watchlists-all"),
    path("watchlist-performance/<path:watchlist_name>/reset-prices/", views.watchlist_reset_prices, name="watchlist-reset-prices"),
    path("watchlist-performance/<path:watchlist_name>/delete/", views.watchlist_delete, name="watchlist-delete"),
    path("watchlist-performance/<path:watchlist_name>/", views.watchlist_detail, name="watchlist-detail"),
    path("news/", views.news, name="news"),
]