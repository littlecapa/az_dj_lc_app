from django.urls import path

from .mcp_server import LeisureMcpView

app_name = 'leisure'

urlpatterns = [
    path('mcp', LeisureMcpView.as_view(), name='mcp'),
]
