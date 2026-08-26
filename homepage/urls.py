from django.urls import path, include
from django.contrib import admin
from . import views

app_name = 'homepage'

urlpatterns = [
    path('', views.index, name='index'),
    path('links/', views.links_page, name='links'),
    path('contact/', views.contact, name='contact'),
    path('my-chess-club/', views.my_chess_club, name='my_chess_club'),
    path('monitoring/', views.monitoring_view, name='monitoring'),
    path('scbb/', views.scbb_monitor_view, name='scbb'),
    path('scbb/check/', views.scbb_check_api, name='scbb-check'),
    path('historical-chess-mags/', views.historical_chess_mags, name='historical-chess-mags'),
    path('historical-chess-mags/check/', views.check_historical_chess_mags, name='check-historical-chess-mags'),
    #
    # Blog
    #
    path('blog/', views.blog.as_view(), name='blog'),
    path('post/<slug:slug>/', views.BlogDetailView.as_view(), name='blog_detail'),
    # Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),
    # API Overview
    path('api-overview/', views.api_overview, name='api-overview'),
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')), 
]
