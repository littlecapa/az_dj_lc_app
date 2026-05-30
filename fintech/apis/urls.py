# fintech/apis/urls.py

from django.urls import path
from fintech.apis.securities import SecurityPriceView
from fintech.apis.cowork import PortfolioView, WatchlistView, AssetPriceHistoryView

app_name = "fintech"

urlpatterns = [
    # Live price fetch (provider chain)
    path("securities/<str:isin>/price", SecurityPriceView.as_view(), name="security-price"),

    # Cowork read-only endpoints
    path("portfolio",                         PortfolioView.as_view(),          name="api-portfolio"),
    path("watchlist",                         WatchlistView.as_view(),          name="api-watchlist"),
    path("assets/<str:isin>/history",         AssetPriceHistoryView.as_view(),  name="api-asset-history"),
]
