from typing import Optional

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def _fernet() -> Fernet:
    return Fernet(settings.MCP_TOKEN_ENCRYPTION_KEY)


class McpConnection(models.Model):
    """
    OAuth-Verbindung zu einem MCP-Server (z.B. Scalable Capital). Ein Datensatz
    pro User+Provider. Discovery-Endpoints/Client-ID werden bei der ersten
    Anmeldung automatisch ermittelt (siehe core.mcp_client), damit weitere
    Provider ohne Codeänderung angebunden werden können.
    """

    class Provider(models.TextChoices):
        SCALABLE = 'scalable', 'Scalable Capital'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='mcp_connections',
        help_text="Besitzer der Verbindung",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    mcp_server_url = models.URLField(help_text="z.B. https://mcp.scalable.capital/mcp")

    authorization_endpoint = models.URLField(blank=True)
    token_endpoint = models.URLField(blank=True)
    registration_endpoint = models.URLField(blank=True)
    client_id = models.CharField(max_length=255, blank=True)
    scopes = models.CharField(max_length=255, default="openid profile offline_access")

    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'provider')
        ordering = ['provider']
        verbose_name = "MCP-Verbindung"
        verbose_name_plural = "MCP-Verbindungen"

    def __str__(self):
        return f"{self.get_provider_display()} ({self.user})"

    @property
    def is_connected(self) -> bool:
        return bool(self.access_token_encrypted)

    @property
    def is_token_expired(self) -> bool:
        return bool(self.token_expires_at) and timezone.now() >= self.token_expires_at

    def set_tokens(self, access_token: str, refresh_token: str = None, expires_in: int = None):
        f = _fernet()
        self.access_token_encrypted = f.encrypt(access_token.encode()).decode()
        if refresh_token:
            self.refresh_token_encrypted = f.encrypt(refresh_token.encode()).decode()
        self.token_expires_at = (
            timezone.now() + timezone.timedelta(seconds=expires_in) if expires_in else None
        )

    def get_access_token(self) -> Optional[str]:
        if not self.access_token_encrypted:
            return None
        return _fernet().decrypt(self.access_token_encrypted.encode()).decode()

    def get_refresh_token(self) -> Optional[str]:
        if not self.refresh_token_encrypted:
            return None
        return _fernet().decrypt(self.refresh_token_encrypted.encode()).decode()
