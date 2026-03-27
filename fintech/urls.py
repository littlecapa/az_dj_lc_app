# fintech/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('api/asset-price/', views.AssetPriceView.as_view(), name='asset_price'),
    path('overview/', views.OverviewView.as_view(), name='overview'),
]