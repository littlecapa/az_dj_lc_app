# fintech/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.fintech_home, name='fintech_home'),
    path('dashboard/', views.fintech_dashboard, name='fintech_dashboard'),
]
