from django.urls import path
from django.views.defaults import server_error
from . import views

app_name = 'homepage'

urlpatterns = [
    path('', views.index, name='index'),
    path('contact/', views.contact, name='contact'),
    path('monitoring/', views.monitoring_view, name='monitoring'),
    path('historical-chess-mags/', views.historical_chess_mags, name='historical-chess-mags'),
]
