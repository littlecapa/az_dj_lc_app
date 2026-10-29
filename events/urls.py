from django.urls import path

from .mcp_server import EventsMcpView

app_name = 'events'

urlpatterns = [
    path('mcp', EventsMcpView.as_view(), name='mcp'),
]
