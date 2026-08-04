from django.urls import path
from . import views

app_name = 'telegram_app'

urlpatterns = [
    path('', views.send_message_view, name='send_message'),
]
