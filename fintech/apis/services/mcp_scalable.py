"""
Kursabfrage über die Scalable-Capital-MCP-Verbindung (core.mcp_client, core.models.McpConnection).

Nutzt den Token, der über littlecapa.com/mcp/scalable/ bzw. scripts/scalable_mcp_local_login.py
für settings.MCP_TARGET_USERNAME hinterlegt wurde. Prüft vor jedem Aufruf lokal (ohne
Netzwerk-Request), ob der Verbindungsstatus "verbunden" ist — vorhandener, nicht abgelaufener
Token — und bricht sonst sofort mit ScalableMcpNotConnectedError ab.

WICHTIG: Noch NICHT in ProviderManager/update_prices eingehängt — bewusst eigenständig,
bis manuell getestet (siehe fintech.management.commands.test_scalable_mcp_price).

Nutzung (Schnittstelle wie andere *Request-Provider, z.B. YahooFinanceRequest):
    from fintech.apis.services.mcp_scalable import ScalableMcpRequest, ScalableMcpNotConnectedError

    price_str, currency = ScalableMcpRequest().isin2price("US0378331005")
"""
import json
import logging
from typing import Tuple

from django.conf import settings
from django.contrib.auth.models import User

from core.mcp_client import McpToolClient, McpClientError
from core.models import McpConnection
from .request_lib import KeyNotFoundWarning, KeyNotFoundError

logger = logging.getLogger(__name__)


class ScalableMcpNotConnectedError(Exception):
    """Kein gültiger (vorhandener, nicht abgelaufener) Scalable-MCP-Token verfügbar."""


class ScalableMcpRequest:
    """Kursabfrage über Scalable Capital MCP (get_security_quote)."""

    id = "scalable_mcp"

    def get_quote(self, isin: str) -> dict:
        """
        Rohes Quote-Dict von get_security_quote (midPrice, currency, isOutdated,
        timestampUtc, ...). isin2price() ist ein dünner Wrapper darum; wer zusätzlich
        z.B. isOutdated braucht (siehe fintech.mcp_benchmark_views — ein "isOutdated"
        Scalable-Kurs erklärt sonst unerklärliche große Preis-Deltas im Benchmark),
        nutzt diese Methode direkt statt isin2price().

        Raises:
            ScalableMcpNotConnectedError: kein gültiger Token vorhanden (fail-fast, kein
                Netzwerk-Aufruf) — Status ist nicht "verbunden".
            KeyNotFoundWarning: MCP-Server/Netzwerk-Fehler (z.B. abgelehnter Token, Timeout).
            KeyNotFoundError: Antwort kam an, enthält aber keinen brauchbaren Kurs.
        """
        connection = self._get_connected_connection()

        try:
            result = McpToolClient(connection).call_tool("get_security_quote", {"isin": isin})
        except McpClientError as exc:
            logger.warning(f"Scalable-MCP get_security_quote fehlgeschlagen für {isin}: {exc}")
            raise KeyNotFoundWarning(isin, message="Scalable MCP quote request failed") from exc

        return self._extract_quote(result, isin)

    def isin2price(self, isin: str) -> Tuple[str, str]:
        """Return (price_str, currency) für *isin* — Mid-Price aus get_security_quote."""
        quote = self.get_quote(isin)
        mid_price = quote.get("midPrice")
        currency = quote.get("currency")
        if mid_price is None or not currency:
            raise KeyNotFoundError(isin, message="Scalable MCP response enthält keinen midPrice/currency")

        if quote.get("isOutdated"):
            logger.warning(
                f"Scalable-MCP-Kurs für {isin} als 'isOutdated' markiert "
                f"(timestampUtc={quote.get('timestampUtc')})"
            )

        return str(mid_price), currency

    # ------------------------------------------------------------------
    def _get_connected_connection(self) -> McpConnection:
        """Lädt die McpConnection für MCP_TARGET_USERNAME und prüft 'verbunden' rein lokal."""
        username = getattr(settings, "MCP_TARGET_USERNAME", None)
        if not username:
            raise ScalableMcpNotConnectedError("settings.MCP_TARGET_USERNAME ist nicht konfiguriert.")

        try:
            user = User.objects.get(username=username)
            connection = McpConnection.objects.get(user=user, provider=McpConnection.Provider.SCALABLE)
        except (User.DoesNotExist, McpConnection.DoesNotExist):
            raise ScalableMcpNotConnectedError(f"Keine Scalable-MCP-Verbindung für User {username!r} vorhanden.")

        if not connection.is_connected or connection.is_token_expired:
            raise ScalableMcpNotConnectedError(
                "Scalable-MCP-Status ist nicht 'verbunden' (kein Token oder abgelaufen) — "
                "zuerst ./trigger_scalable.sh ausführen."
            )
        return connection

    @staticmethod
    def _extract_quote(result: dict, isin: str) -> dict:
        """structuredContent.security.quote ist die primäre Quelle; content[0].text (JSON-String) als Fallback."""
        structured = result.get("structuredContent") or {}
        quote = structured.get("security", {}).get("quote")
        if quote:
            return quote

        for block in result.get("content", []):
            if block.get("type") == "text":
                try:
                    parsed = json.loads(block["text"])
                except (json.JSONDecodeError, TypeError):
                    continue
                quote = parsed.get("security", {}).get("quote")
                if quote:
                    return quote

        raise KeyNotFoundError(isin, message="Scalable MCP response enthält kein security.quote")
