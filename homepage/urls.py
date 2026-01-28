from django.urls import path
from django.views.defaults import server_error
from . import views

app_name = 'homepage'

urlpatterns = [
    path('', views.index, name='index'),
    path('contact/', views.contact, name='contact'),
    path('my-chess-club/', views.my_chess_club, name='my_chess_club'),
    path('monitoring/', views.monitoring_view, name='monitoring'),
    path('historical-chess-mags/', views.historical_chess_mags, name='historical-chess-mags'),
    #
    # Blog
    #
    path('blog/', views.blog.as_view(), name='blog'),
    path('post/<slug:slug>/', views.BlogDetailView.as_view(), name='blog_detail'),
]
