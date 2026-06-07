# fintech/apis/urls.py

from django.urls import path
from fintech.apis.securities import SecurityPriceView
from fintech.apis.cowork import PortfolioView, WatchlistView, AssetPriceHistoryView
from fintech.apis.watchlist_api import (
    WatchlistCreateView, WatchlistEntryCreateView,
    WatchlistEntryDeleteView, WatchlistDeleteView,
)
from fintech.apis.quicklink_api import QuickLinkImportView
from fintech.apis.asset_api import AssetResolveNameView, AssetResolveNamesView, AssetUpdateView
from fintech.apis.week52_api import Week52View, NewsListView, NewsMarkReadView

app_name = "fintech"

urlpatterns = [
    # Live price fetch (provider chain)
    path("securities/<str:isin>/price", SecurityPriceView.as_view(), name="security-price"),

    # Cowork read-only endpoints
    path("portfolio",                 PortfolioView.as_view(),         name="api-portfolio"),
    path("watchlist",                 WatchlistView.as_view(),         name="api-watchlist"),
    path("assets/<str:isin>/history", AssetPriceHistoryView.as_view(), name="api-asset-history"),

    # Watchlist write/delete endpoints
    path("watchlist/create",                                    WatchlistCreateView.as_view(),       name="api-watchlist-create"),
    path("watchlist/<str:watchlist_name>/entries",              WatchlistEntryCreateView.as_view(),  name="api-watchlist-entries"),
    path("watchlist/<str:watchlist_name>/entries/<str:isin>",   WatchlistEntryDeleteView.as_view(),  name="api-watchlist-entry-delete"),
    path("watchlist/<str:watchlist_name>",                      WatchlistDeleteView.as_view(),       name="api-watchlist-delete"),

    # QuickLink import
    path("quicklinks/import", QuickLinkImportView.as_view(), name="api-quicklinks-import"),

    # Asset name resolution via Yahoo Finance
    path("assets/resolve-names",           AssetResolveNamesView.as_view(), name="api-assets-resolve-names"),
    path("assets/<str:isin>/resolve-name", AssetResolveNameView.as_view(),  name="api-asset-resolve-name"),

    # Asset manual update (PATCH)
    path("assets/<str:isin>",              AssetUpdateView.as_view(),        name="api-asset-update"),

    # 52-Wochen-Range (lazy fetch + DB cache)
    path("assets/<str:isin>/week52",       Week52View.as_view(),             name="api-week52"),

    # News-Events
    path("news",                           NewsListView.as_view(),           name="api-news"),
    path("news/<int:pk>/read",             NewsMarkReadView.as_view(),       name="api-news-read"),
]
