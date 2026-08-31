from django.contrib import admin

from .models import McpConnection


@admin.register(McpConnection)
class McpConnectionAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'mcp_server_url', 'is_connected', 'token_expires_at', 'verified_at', 'updated_at')
    list_filter = ('provider',)
    search_fields = ('user__username', 'mcp_server_url')
    # access_token_encrypted/refresh_token_encrypted/token_expires_at bewusst editierbar:
    # ermöglicht das manuelle Einspielen von Tokens, die außerhalb des Web-Login-Flows
    # beschafft wurden (z.B. via scripts/scalable_mcp_local_login.py, solange die
    # littlecapa.com-Redirect-URI noch nicht auf Scalables Allowlist steht).
    readonly_fields = ('created_at', 'updated_at')
