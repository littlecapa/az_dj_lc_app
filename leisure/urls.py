from django.urls import path

from . import views
from .mcp_server import LeisureMcpView, LeisureWriteMcpView

app_name = 'leisure'

urlpatterns = [
    path('', views.index, name='index'),
    path('mcp', LeisureMcpView.as_view(), name='mcp'),
    path('mcp/write', LeisureWriteMcpView.as_view(), name='mcp-write'),
    path('new_artists', views.new_artists, name='new-artists'),
    path('new_venues', views.new_venues, name='new-venues'),
    path('new_events', views.new_events, name='new-events'),
    path('new_events/voting', views.event_voting, name='event-voting'),
]
