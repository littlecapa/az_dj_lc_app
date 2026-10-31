from django.urls import path

from . import views
from .mcp_server import LeisureMcpView, LeisureWriteMcpView

app_name = 'leisure'

urlpatterns = [
    path('mcp', LeisureMcpView.as_view(), name='mcp'),
    path('mcp/write', LeisureWriteMcpView.as_view(), name='mcp-write'),
    path('new_artists', views.new_artists, name='new-artists'),
]
