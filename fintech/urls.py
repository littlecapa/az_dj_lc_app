# fintech/urls.py

from django.urls import path, include
from . import views

urlpatterns = [
    path('overview/', views.OverviewView.as_view(), name='overview'),
    path('api/', include('fintech.apis.urls')),
]