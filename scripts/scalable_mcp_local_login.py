#!/usr/bin/env python3
"""
Lokaler PoC-Login für die Scalable-Capital-MCP-Anbindung.

Hintergrund: Scalable lässt Dynamic Client Registration für Web-Clients nur mit
Redirect-URIs von einer vorab freigegebenen Allowlist zu (littlecapa.com steht
dort noch nicht drauf, siehe Fehler "Web clients may only register exact
redirect URIs from the approved SaaS allowlist."). Loopback-Redirect-URIs
(127.0.0.1) sind davon ausgenommen (RFC 8252, "native app"-Muster) und
funktionieren sofort ohne Freigabe.

Dieses Skript führt den kompletten OAuth-Flow lokal aus (Login + 2FA passiert
in deinem Browser auf Scalables eigener Seite), ruft danach testweise
get_security_quote auf, und gibt am Ende Fernet-verschlüsselte Tokens aus, die
sich direkt in den Django-Admin (McpConnection) einfügen lassen — damit auch
die deployte /mcp/scalable/-Seite ("Get Quote") funktioniert, bis die echte
littlecapa.com-Redirect-URI bei Scalable freigeschaltet ist.

Nutzung:
    python3 scripts/scalable_mcp_local_login.py [--isin IE00B4L5Y983]

Voraussetzung: MCP_TOKEN_ENCRYPTION_KEY muss in .env stehen (wie in Django).
"""
import argparse
import base64
import datetime
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from cryptography.fernet import Fernet
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.mcp_client import discover_oauth_metadata, register_oauth_client, McpClientError, McpToolClient  # noqa: E402

SCALABLE_MCP_URL = "https://mcp.scalable.capital/mcp"
LOOPBACK_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{LOOPBACK_PORT}/callback"
CLIENT_NAME = "littlecapa.com (lokaler PoC-Login)"
SCOPES = "openid profile offline_access"
CALLBACK_TIMEOUT = 300  # Sekunden


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result = {}

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        _CallbackHandler.result = {k: v[0] for k, v in query.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<html><body><p>Login abgeschlossen - dieses Tab kannst du schliessen.</p></body></html>")

    def log_message(self, format, *args):
        pass  # kein Access-Log für den lokalen Callback-Server nötig


def wait_for_callback(port: int) -> dict:
    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = CALLBACK_TIMEOUT
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    thread.join(timeout=CALLBACK_TIMEOUT)
    return _CallbackHandler.result


class _StaticConnection:
    """Minimaler Connection-Stand-in für McpToolClient.call_tool() ohne Django/DB."""

    def __init__(self, mcp_server_url: str, access_token: str):
        self.mcp_server_url = mcp_server_url
        self.is_token_expired = False
        self._access_token = access_token

    def get_access_token(self):
        return self._access_token


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--isin", default="IE00B4L5Y983",
        help="ISIN für den Test-Quote-Call (Default: iShares Core MSCI World)",
    )
    args = parser.parse_args()

    load_dotenv()
    fernet_key = os.getenv("MCP_TOKEN_ENCRYPTION_KEY")
    if not fernet_key:
        sys.exit("MCP_TOKEN_ENCRYPTION_KEY fehlt in .env")
    fernet = Fernet(fernet_key)

    print(f"1/5 Discovery gegen {SCALABLE_MCP_URL} ...")
    try:
        meta = discover_oauth_metadata(SCALABLE_MCP_URL)
    except McpClientError as exc:
        sys.exit(f"Discovery fehlgeschlagen: {exc}")
    print(f"    authorization_endpoint: {meta['authorization_endpoint']}")
    print(f"    token_endpoint:         {meta['token_endpoint']}")

    print("2/5 Dynamic Client Registration (Loopback-Redirect) ...")
    try:
        client_id = register_oauth_client(meta["registration_endpoint"], REDIRECT_URI, CLIENT_NAME)
    except McpClientError as exc:
        sys.exit(f"Registrierung fehlgeschlagen: {exc}")
    print(f"    client_id: {client_id}")

    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = _b64url(secrets.token_bytes(24))
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{meta['authorization_endpoint']}?{urlencode(params)}"

    print("3/5 Öffne Browser zum Login bei Scalable (inkl. 2FA) ...")
    print(f"    Falls sich nichts öffnet, manuell aufrufen:\n    {auth_url}\n")
    webbrowser.open(auth_url)

    print(f"    Warte auf Redirect an {REDIRECT_URI} (bis zu {CALLBACK_TIMEOUT // 60} Minuten) ...")
    result = wait_for_callback(LOOPBACK_PORT)

    if "error" in result:
        sys.exit(f"Login abgelehnt: {result['error']} ({result.get('error_description', '')})")
    if not result:
        sys.exit("Timeout — kein Callback erhalten.")
    if result.get("state") != state:
        sys.exit("State-Mismatch — Login abgebrochen.")
    code = result.get("code")
    if not code:
        sys.exit(f"Kein 'code' im Callback erhalten: {result}")

    print("4/5 Tausche Code gegen Token ...")
    token_resp = requests.post(
        meta["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if token_resp.status_code >= 400:
        sys.exit(f"Token-Tausch fehlgeschlagen ({token_resp.status_code}): {token_resp.text}")
    token_data = token_resp.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in")
    print("    OK, Access-Token erhalten.")

    print(f"5/5 Test-Call get_security_quote(isin={args.isin!r}) ...")
    try:
        quote_result = McpToolClient(_StaticConnection(SCALABLE_MCP_URL, access_token)).call_tool(
            "get_security_quote", {"isin": args.isin}
        )
        print("    Ergebnis:")
        print(json.dumps(quote_result, indent=2, ensure_ascii=False))
    except McpClientError as exc:
        print(f"    Tool-Call fehlgeschlagen: {exc} (detail: {exc.detail})")

    access_token_encrypted = fernet.encrypt(access_token.encode()).decode()
    refresh_token_encrypted = fernet.encrypt(refresh_token.encode()).decode() if refresh_token else ""
    expires_at = (
        (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)).isoformat()
        if expires_in else ""
    )

    print("\n" + "=" * 78)
    print("Werte zum Einfügen in Django-Admin -> Core -> Mcp-Verbindungen")
    print("(bestehenden 'scalable'-Datensatz für deinen User bearbeiten, oder neu anlegen):")
    print("=" * 78)
    for label, value in [
        ("provider", "scalable"),
        ("mcp_server_url", SCALABLE_MCP_URL),
        ("authorization_endpoint", meta["authorization_endpoint"]),
        ("token_endpoint", meta["token_endpoint"]),
        ("registration_endpoint", meta["registration_endpoint"]),
        ("client_id", client_id),
        ("scopes", SCOPES),
        ("access_token_encrypted", access_token_encrypted),
        ("refresh_token_encrypted", refresh_token_encrypted),
        ("token_expires_at (UTC)", expires_at),
    ]:
        print(f"{label}:\n  {value}\n")
    print("=" * 78)
    print(
        "Hinweis: client_id ist an die Loopback-Redirect-URI gebunden, Refresh-Token-\n"
        "Anfragen brauchen aber keine redirect_uri — automatisches Token-Refresh über\n"
        "die Django-App funktioniert daher trotzdem. Sobald littlecapa.com auf der\n"
        "Scalable-Allowlist steht, einmal über den echten Login-Button neu verbinden."
    )


if __name__ == "__main__":
    main()
