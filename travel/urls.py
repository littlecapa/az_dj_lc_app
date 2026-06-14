from django.urls import path
from . import views

app_name = 'travel'

urlpatterns = [
    path('', views.index, name='index'),
    path('flight_search/', views.flight_search, name='flight-search'),
    path('route_search/', views.route_search, name='route-search'),
    path('return_flights/', views.return_flights_ajax, name='return-flights-ajax'),
    path('airport_lookup/', views.airport_lookup, name='airport-lookup'),
]
