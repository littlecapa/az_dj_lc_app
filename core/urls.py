from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("jira/", views.jira_page, name="jira"),
    path("mcp/", views.mcp_index, name="mcp_index"),
    path("mcp/callback/", views.mcp_callback, name="mcp_callback"),
    path("mcp/scalable/", views.mcp_scalable_page, name="mcp_scalable"),
    path("mcp/scalable/login/", views.mcp_scalable_login, name="mcp_scalable_login"),
    path("mcp/scalable/import-token/", views.mcp_scalable_import_token, name="mcp_scalable_import_token"),
    path("mcp/scalable/logout/", views.mcp_scalable_logout, name="mcp_scalable_logout"),
    path("mcp/scalable/command/", views.mcp_scalable_command, name="mcp_scalable_command"),
]
