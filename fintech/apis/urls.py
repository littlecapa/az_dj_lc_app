# fintech/apis/urls.py

from django.urls import path
from fintech.apis.securities import SecurityPriceView
from fintech.apis.cowork import PortfolioView, WatchlistView, AssetPriceHistoryView
from fintech.apis.watchlist_api import WatchlistCreateView, WatchlistEntryCreateView
from fintech.apis.quicklink_api import QuickLinkImportView

app_name = "fintech"

urlpatterns = [
    # Live price fetch (provider chain)
    path("securities/<str:isin>/price", SecurityPriceView.as_view(), name="security-price"),

    # Cowork read-only endpoints
    path("portfolio",                 PortfolioView.as_view(),         name="api-portfolio"),
    path("watchlist",                 WatchlistView.as_view(),         name="api-watchlist"),
    path("assets/<str:isin>/history", AssetPriceHistoryView.as_view(), name="api-asset-history"),

    # Watchlist write endpoints
    path("watchlist/create",                       WatchlistCreateView.as_view(),      name="api-watchlist-create"),
    path("watchlist/<str:watchlist_name>/entries", WatchlistEntryCreateView.as_view(), name="api-watchlist-entries"),

    # QuickLink import
    path("quicklinks/import", QuickLinkImportView.as_view(), name="api-quicklinks-import"),
]
