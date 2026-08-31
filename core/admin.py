from django.contrib import admin

from .models import McpConnection


@admin.register(McpConnection)
class McpConnectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'mcp_server_url', 'is_connected', 'token_expires_at', 'updated_at')
    list_filter = ('provider',)
    search_fields = ('user__username', 'mcp_server_url')
    readonly_fields = (
        'access_token_encrypted', 'refresh_token_encrypted', 'token_expires_at',
        'created_at', 'updated_at',
    )
