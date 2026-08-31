"""
Generischer OAuth-2.1- + JSON-RPC-Client für MCP-Server (Streamable-HTTP-Transport,
siehe https://modelcontextprotocol.io). Aktuell an Scalable Capital angebunden, aber
bewusst provider-unabhängig gehalten (Discovery + Dynamic Client Registration statt
fest verdrahteter Endpoints), da weitere MCP-Server folgen sollen. Konfiguration und
Tokens liegen in core.models.McpConnection.

Nutzung:
    from core.mcp_client import McpOAuthFlow, McpToolClient, McpClientError

    flow = McpOAuthFlow(connection)
    flow.ensure_configured(redirect_uri, "littlecapa.com")
    auth_url, pkce_state = flow.build_authorization_url(redirect_uri)
    # ... Redirect, Callback ...
    flow.exchange_code(code, redirect_uri, pkce_state["code_verifier"])

    result = McpToolClient(connection).call_tool("get_security_quote", {"isin": "..."})
"""
import base64
import hashlib
import json
import logging
import re
import secrets
from typing import Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15  # Sekunden
MCP_PROTOCOL_VERSION = "2025-06-18"


class McpClientError(Exception):
    """Einheitlicher Fehlertyp für Discovery-, Auth- und Tool-Call-Fehler."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def has_valid_token(connection) -> bool:
    """Token vorhanden UND noch nicht abgelaufen (unbekannte Ablaufzeit zählt als gültig)."""
    return connection.is_connected and not connection.is_token_expired


def _get_json(url: str) -> dict:
    try:
        resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise McpClientError(f"Abruf von {url} fehlgeschlagen: {exc}") from exc
    return resp.json()


def discover_oauth_metadata(mcp_server_url: str) -> dict:
    """
    Ermittelt authorization_endpoint/token_endpoint/registration_endpoint eines
    MCP-Servers per RFC 9728 (Protected Resource Metadata) + RFC 8414 (Authorization
    Server Metadata): unauthentifizierte Anfrage -> 401 mit WWW-Authenticate ->
    resource_metadata-URL -> authorization_servers -> .well-known/oauth-authorization-server.
    """
    try:
        resp = requests.post(
            mcp_server_url,
            json={"jsonrpc": "2.0", "id": 0, "method": "ping"},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise McpClientError(f"MCP-Server nicht erreichbar: {exc}") from exc

    # WWW-Authenticate: Bearer resource_metadata="...", weitere_param="..." — Parameter sind
    # kommasepariert, aber durch das führende Auth-Scheme ("Bearer ") per Leerzeichen getrennt.
    match = re.search(r'resource_metadata="([^"]+)"', resp.headers.get("WWW-Authenticate", ""))
    resource_metadata_url = match.group(1) if match else None

    if not resource_metadata_url:
        raise McpClientError(
            "Konnte OAuth-Metadaten nicht finden (kein 'resource_metadata' im "
            "WWW-Authenticate-Header der 401-Antwort)."
        )

    resource_meta = _get_json(resource_metadata_url)
    auth_servers = resource_meta.get("authorization_servers") or []
    if not auth_servers:
        raise McpClientError("Resource-Metadata enthält keinen authorization_server.")

    issuer = auth_servers[0].rstrip("/")
    as_meta = _get_json(f"{issuer}/.well-known/oauth-authorization-server")

    try:
        return {
            "authorization_endpoint": as_meta["authorization_endpoint"],
            "token_endpoint": as_meta["token_endpoint"],
            "registration_endpoint": as_meta.get("registration_endpoint", ""),
        }
    except KeyError as exc:
        raise McpClientError(f"Authorization-Server-Metadata unvollständig: fehlt {exc}") from exc


def register_oauth_client(registration_endpoint: str, redirect_uri: str, client_name: str) -> str:
    """Dynamic Client Registration (RFC 7591). Gibt die vergebene client_id zurück."""
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    try:
        resp = requests.post(registration_endpoint, json=payload, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise McpClientError(f"Client-Registrierung fehlgeschlagen: {exc}") from exc

    if resp.status_code >= 400:
        raise McpClientError(
            f"Client-Registrierung fehlgeschlagen ({resp.status_code})",
            status_code=resp.status_code, detail=resp.text,
        )

    client_id = resp.json().get("client_id")
    if not client_id:
        raise McpClientError("Registrierungs-Antwort enthält keine client_id.", detail=resp.text)
    return client_id


class McpOAuthFlow:
    """Kapselt Discovery, Dynamic Client Registration und PKCE-Authorization-Code-Flow für eine McpConnection."""

    def __init__(self, connection):
        self.connection = connection

    def ensure_configured(self, redirect_uri: str, client_name: str) -> None:
        """Führt Discovery + Dynamic Client Registration aus, falls noch nicht geschehen. Speichert die Connection."""
        conn = self.connection
        if not conn.authorization_endpoint or not conn.token_endpoint:
            meta = discover_oauth_metadata(conn.mcp_server_url)
            conn.authorization_endpoint = meta["authorization_endpoint"]
            conn.token_endpoint = meta["token_endpoint"]
            conn.registration_endpoint = meta["registration_endpoint"]

        if not conn.client_id and conn.registration_endpoint:
            conn.client_id = register_oauth_client(conn.registration_endpoint, redirect_uri, client_name)

        conn.save()

    def build_authorization_url(self, redirect_uri: str) -> tuple[str, dict]:
        """
        Erzeugt PKCE-Verifier/Challenge + State und gibt (authorize_url, pkce_state) zurück.
        pkce_state gehört in die Session (flüchtig, nicht Teil der dauerhaften Config) und
        muss beim Callback an exchange_code() übergeben werden.
        """
        verifier = _b64url(secrets.token_bytes(64))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        state = _b64url(secrets.token_bytes(24))

        params = {
            "response_type": "code",
            "client_id": self.connection.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.connection.scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        url = f"{self.connection.authorization_endpoint}?{urlencode(params)}"
        pkce_state = {"code_verifier": verifier, "state": state, "connection_id": self.connection.id}
        return url, pkce_state

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> None:
        """Tauscht den Autorisierungscode gegen Access-/Refresh-Token und speichert sie verschlüsselt."""
        data = self._post_token({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.connection.client_id,
            "code_verifier": code_verifier,
        })
        self.connection.set_tokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )
        self.connection.save()

    def refresh(self) -> None:
        """Holt per refresh_token-Grant ein neues Access-Token."""
        refresh_token = self.connection.get_refresh_token()
        if not refresh_token:
            raise McpClientError("Kein Refresh-Token vorhanden — bitte erneut einloggen.")

        data = self._post_token({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.connection.client_id,
        })
        self.connection.set_tokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
        )
        self.connection.save()

    def _post_token(self, payload: dict) -> dict:
        try:
            resp = requests.post(
                self.connection.token_endpoint,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise McpClientError(f"Token-Endpoint nicht erreichbar: {exc}") from exc

        if resp.status_code >= 400:
            raise McpClientError(
                f"Token-Anfrage fehlgeschlagen ({resp.status_code})",
                status_code=resp.status_code, detail=resp.text,
            )
        return resp.json()


def _parse_json_rpc_response(resp: requests.Response) -> dict:
    """MCP-Streamable-HTTP-Server dürfen JSON oder eine einzelne SSE-'data:'-Zeile zurückgeben."""
    if "text/event-stream" in resp.headers.get("Content-Type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
        raise McpClientError("Leere SSE-Antwort vom MCP-Server erhalten.")
    return resp.json()


class McpToolClient:
    """Führt einen einzelnen MCP-Tool-Call aus (initialize -> initialized -> tools/call)."""

    def __init__(self, connection):
        self.connection = connection

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        conn = self.connection
        if conn.is_token_expired:
            McpOAuthFlow(conn).refresh()

        token = conn.get_access_token()
        if not token:
            raise McpClientError("Keine gültige MCP-Verbindung — bitte erneut einloggen.")

        session_id = self._initialize(conn.mcp_server_url, token)
        return self._call(conn.mcp_server_url, token, session_id, tool_name, arguments)

    def verify(self) -> None:
        """Prüft nur, ob der gespeicherte Token beim MCP-Server gültig ist (initialize-Handshake, kein Tool-Call)."""
        conn = self.connection
        if conn.is_token_expired:
            McpOAuthFlow(conn).refresh()

        token = conn.get_access_token()
        if not token:
            raise McpClientError("Keine gültige MCP-Verbindung — bitte erneut einloggen.")

        self._initialize(conn.mcp_server_url, token)

    @staticmethod
    def _headers(token: str, session_id: Optional[str] = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        return headers

    def _initialize(self, url: str, token: str) -> Optional[str]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "az_dj_lc_app", "version": "1.0"},
            },
        }
        resp = self._post(url, self._headers(token), payload)
        _parse_json_rpc_response(resp)
        session_id = resp.headers.get("Mcp-Session-Id")

        notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._post(url, self._headers(token, session_id), notify)
        return session_id

    def _call(self, url: str, token: str, session_id: Optional[str], tool_name: str, arguments: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = self._post(url, self._headers(token, session_id), payload)
        data = _parse_json_rpc_response(resp)
        if "error" in data:
            raise McpClientError(data["error"].get("message", "MCP-Fehler"), detail=data["error"])
        return data.get("result", {})

    @staticmethod
    def _post(url: str, headers: dict, payload: dict) -> requests.Response:
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise McpClientError(f"MCP-Server nicht erreichbar: {exc}") from exc

        if resp.status_code == 401:
            raise McpClientError("MCP-Token abgelehnt (401) — bitte erneut einloggen.", status_code=401)
        if resp.status_code >= 400:
            raise McpClientError(
                f"MCP-Anfrage fehlgeschlagen ({resp.status_code})",
                status_code=resp.status_code, detail=resp.text,
            )
        return resp
