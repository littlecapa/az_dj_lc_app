# fintech/urls.py

from django.urls import path, include
from . import views

urlpatterns = [
    path('api/', include('fintech.apis.urls')),
    path("export", views.portfolio_export, name="portfolio-export"),
]