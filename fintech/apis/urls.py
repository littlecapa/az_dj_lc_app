# fintech/apis/urls.py

from django.urls import path
from fintech.apis.securities import SecurityPriceView

app_name = "fintech"

urlpatterns = [
    # GET /fintech/securities/{isin}/price?type=Stock
    path("securities/<str:isin>/price", SecurityPriceView.as_view(), name="security-price"),
]
