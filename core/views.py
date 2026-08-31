import hmac
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from .jira_client import JiraClient, JiraApiError
from .mcp_client import McpOAuthFlow, McpToolClient, McpClientError, discover_oauth_metadata
from .models import McpConnection

logger = logging.getLogger(__name__)

JIRA_ISSUE_TYPES = ["Task", "Bug", "Story", "Feature", "Epic"]
DELETE_RANGE_PROJECT_KEY = "FIN"
DELETE_RANGE_MAX = 50  # Sicherheitsgrenze pro Löschvorgang

MCP_CLIENT_NAME = "littlecapa.com"
MCP_PROVIDER_DEFAULTS = {
    McpConnection.Provider.SCALABLE: "https://mcp.scalable.capital/mcp",
}


@never_cache
@login_required
def jira_page(request):
    """Seite zum Anlegen neuer Jira-Tickets und Ergänzen bestehender per Kommentar."""
    if request.method == "POST":
        form_type = request.POST.get("form_type")

        try:
            client = JiraClient()
        except JiraApiError as exc:
            request.session["jira_result"] = {"ok": False, "message": str(exc)}
            return redirect("core:jira")

        if form_type == "create":
            summary = request.POST.get("summary", "").strip()
            description = request.POST.get("description", "").strip()
            issue_type = request.POST.get("issue_type", "Task").strip()
            project_key = request.POST.get("project_key", "").strip() or None

            if not summary:
                request.session["jira_result"] = {
                    "ok": False, "message": "Zusammenfassung darf nicht leer sein.",
                }
                return redirect("core:jira")

            try:
                issue = client.create_issue(
                    summary=summary,
                    description=description,
                    issue_type=issue_type,
                    project_key=project_key,
                )
                request.session["jira_result"] = {
                    "ok": True,
                    "message": f"Ticket {issue['key']} angelegt.",
                    "key": issue["key"],
                    "url": issue["url"],
                }
            except JiraApiError as exc:
                logger.warning(f"Jira create_issue fehlgeschlagen: {exc}")
                request.session["jira_result"] = {
                    "ok": False, "message": str(exc), "detail": str(exc.detail) if exc.detail else None,
                }

        elif form_type == "comment":
            issue_key = request.POST.get("issue_key", "").strip().upper()
            comment = request.POST.get("comment", "").strip()

            if not issue_key or not comment:
                request.session["jira_result"] = {
                    "ok": False, "message": "Ticket-Key und Kommentar sind erforderlich.",
                }
                return redirect("core:jira")

            try:
                client.add_comment(issue_key, comment)
                request.session["jira_result"] = {
                    "ok": True,
                    "message": f"Kommentar zu {issue_key} hinzugefügt.",
                    "key": issue_key,
                    "url": f"{client.base_url}/browse/{issue_key}",
                }
            except JiraApiError as exc:
                logger.warning(f"Jira add_comment fehlgeschlagen: {exc}")
                request.session["jira_result"] = {
                    "ok": False, "message": str(exc), "detail": str(exc.detail) if exc.detail else None,
                }

        elif form_type == "delete_range":
            from_raw = request.POST.get("from_num", "").strip()
            to_raw = request.POST.get("to_num", "").strip()

            if not from_raw.isdigit() or not to_raw.isdigit():
                request.session["jira_result"] = {
                    "ok": False, "message": "'von' und 'bis' müssen positive Zahlen sein.",
                }
                return redirect("core:jira")

            von, bis = int(from_raw), int(to_raw)
            if von < 1 or bis < von:
                request.session["jira_result"] = {
                    "ok": False, "message": "'von' muss ≥ 1 und ≤ 'bis' sein.",
                }
                return redirect("core:jira")
            if bis - von + 1 > DELETE_RANGE_MAX:
                request.session["jira_result"] = {
                    "ok": False,
                    "message": (
                        f"Bereich umfasst {bis - von + 1} Tickets, maximal {DELETE_RANGE_MAX} "
                        f"pro Durchlauf erlaubt — bitte in kleineren Blöcken löschen."
                    ),
                }
                return redirect("core:jira")

            items = []
            deleted = 0
            for i in range(von, bis + 1):
                key = f"{DELETE_RANGE_PROJECT_KEY}-{i}"
                try:
                    client.transition_issue_to_done(key)
                    client.delete_issue(key)
                    items.append({"key": key, "status": "deleted", "detail": None})
                    deleted += 1
                except JiraApiError as exc:
                    logger.warning(f"Löschen von {key} fehlgeschlagen: {exc}")
                    items.append({"key": key, "status": "error", "detail": str(exc)})

            errors = len(items) - deleted
            request.session["jira_result"] = {
                "ok": errors == 0,
                "message": f"{deleted} Ticket(s) auf Done gesetzt und gelöscht, {errors} Fehler.",
                "items": items,
            }

        return redirect("core:jira")

    result = request.session.pop("jira_result", None)
    return render(request, "core/jira.html", {
        "result": result,
        "issue_types": JIRA_ISSUE_TYPES,
        "default_project_key": getattr(settings, "JIRA_PROJECT_KEY", ""),
        "delete_range_max": DELETE_RANGE_MAX,
    })


# ----------------------------------------------------------------------
# MCP (Model Context Protocol) — Broker-Anbindungen per OAuth, aktuell Scalable Capital.
# Weitere Provider: Eintrag in MCP_PROVIDER_DEFAULTS + eigene Seite/URLs analog "scalable".

@login_required
def mcp_index(request):
    """Übersicht aller MCP-Provider und ob der eingeloggte User jeweils verbunden ist."""
    connected_providers = set(
        McpConnection.objects.filter(user=request.user, access_token_encrypted__gt="")
        .values_list("provider", flat=True)
    )
    providers = [
        {
            "label": McpConnection.Provider.SCALABLE.label,
            "url_name": "core:mcp_scalable",
            "connected": McpConnection.Provider.SCALABLE in connected_providers,
        },
    ]
    return render(request, "core/mcp_index.html", {"providers": providers})


def _get_or_create_connection(request, provider):
    connection, _ = McpConnection.objects.get_or_create(
        user=request.user,
        provider=provider,
        defaults={"mcp_server_url": MCP_PROVIDER_DEFAULTS[provider]},
    )
    return connection


def _has_valid_token(connection) -> bool:
    """Token vorhanden UND noch nicht abgelaufen (unbekannte Ablaufzeit zählt als gültig)."""
    return connection.is_connected and not connection.is_token_expired


@never_cache
@login_required
def mcp_scalable_page(request):
    """
    Seite für die Scalable-Capital-MCP-Verbindung. Drei Zustände:
    - kein gültiger Token in der DB -> "nicht verbunden", Login-Button deaktiviert
    - gültiger Token vorhanden, aber diese Session hat ihn noch nicht live geprüft -> "bereit",
      Login-Button aktiv, Token-/Client-Werte werden angezeigt
    - Login gedrückt und initialize-Handshake erfolgreich -> "verbunden", Kommando-Formular sichtbar
    """
    connection = _get_or_create_connection(request, McpConnection.Provider.SCALABLE)
    result = request.session.pop("mcp_result", None)
    has_valid_token = _has_valid_token(connection)
    connected = has_valid_token and request.session.get("mcp_scalable_connected", False)

    context = {
        "connection": connection,
        "result": result,
        "has_valid_token": has_valid_token,
        "connected": connected,
    }
    if has_valid_token:
        context["access_token"] = connection.get_access_token()
        context["refresh_token"] = connection.get_refresh_token()
        # ISO-8601 mit UTC-Offset, damit JS im Browser lokale Zeit + Countdown korrekt berechnet.
        context["token_expires_at_iso"] = connection.token_expires_at.isoformat() if connection.token_expires_at else None

    return render(request, "core/mcp_scalable.html", context)


@login_required
@require_POST
def mcp_scalable_connect(request):
    """
    Prüft den in der DB gespeicherten Token live gegen Scalable (initialize-Handshake,
    kein Tool-Call) und markiert die Browser-Session als verbunden. Ersetzt für den
    Alltag den OAuth-Redirect-Login (core:mcp_scalable_login), solange littlecapa.com
    nicht auf Scalables Redirect-Allowlist steht — der Token kommt stattdessen von
    scripts/scalable_mcp_local_login.py (per Push oder manuellem Formular).
    """
    connection = _get_or_create_connection(request, McpConnection.Provider.SCALABLE)

    if not _has_valid_token(connection):
        request.session["mcp_scalable_connected"] = False
        request.session["mcp_result"] = {
            "ok": False,
            "message": "Kein gültiger Token vorhanden — zuerst ./trigger_scalable.sh ausführen.",
        }
        return redirect("core:mcp_scalable")

    try:
        McpToolClient(connection).verify()
        request.session["mcp_scalable_connected"] = True
        request.session["mcp_result"] = {"ok": True, "message": "Erfolgreich mit Scalable verbunden."}
    except McpClientError as exc:
        logger.warning(f"MCP-Connect (Scalable) fehlgeschlagen: {exc}")
        request.session["mcp_scalable_connected"] = False
        request.session["mcp_result"] = {"ok": False, "message": str(exc)}

    return redirect("core:mcp_scalable")


def _apply_token_import(connection, access_token, refresh_token, client_id, expires_at):
    """
    Gemeinsame Übernahme-Logik für importierte Tokens (manuelles Formular + REST-API),
    da beide Wege exakt dasselbe tun müssen: Discovery nachholen, Client-ID setzen,
    Tokens verschlüsselt speichern.
    """
    # token_endpoint wird für spätere automatische Refreshs gebraucht (McpOAuthFlow.refresh);
    # beim regulären Login-Flow käme das aus ensure_configured(), hier holen wir es separat nach.
    if not connection.token_endpoint:
        try:
            meta = discover_oauth_metadata(connection.mcp_server_url)
            connection.authorization_endpoint = meta["authorization_endpoint"]
            connection.token_endpoint = meta["token_endpoint"]
            connection.registration_endpoint = meta["registration_endpoint"]
        except McpClientError as exc:
            logger.warning(f"Discovery beim Token-Import fehlgeschlagen: {exc}")

    if client_id:
        connection.client_id = client_id

    connection.set_tokens(access_token=access_token, refresh_token=refresh_token or None)
    if expires_at:
        connection.token_expires_at = expires_at
    connection.save()


@csrf_exempt
@require_http_methods(["PUT"])
def mcp_scalable_api_import_token(request):
    """
    Nimmt frische Tokens von scripts/scalable_mcp_local_login.py entgegen (--push, Default
    an) und speichert sie über _apply_token_import(). Auth über X-Api-Key-Header
    (settings.MCP_IMPORT_API_KEY) statt Session-Login, da der Aufruf von einem Skript
    kommt, nicht aus dem Browser — daher auch CSRF-exempt.

    Erwarteter JSON-Body: {"username", "access_token", "refresh_token"?, "client_id"?,
    "token_expires_at"?} — token_expires_at als ISO-8601-String (UTC).
    """
    api_key = getattr(settings, "MCP_IMPORT_API_KEY", None)
    provided = request.headers.get("X-Api-Key", "")
    if not api_key or not hmac.compare_digest(provided, api_key):
        return JsonResponse({"error": "Unauthorized", "detail": "Valid X-Api-Key header required."}, status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    username = payload.get("username", "").strip()
    access_token = payload.get("access_token", "").strip()
    if not username or not access_token:
        return JsonResponse({"error": "'username' und 'access_token' sind erforderlich."}, status=400)

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({"error": f"User {username!r} nicht gefunden."}, status=404)

    expires_at = None
    expires_at_raw = payload.get("token_expires_at")
    if expires_at_raw:
        expires_at = parse_datetime(expires_at_raw)
        if expires_at is None:
            return JsonResponse({"error": "'token_expires_at' ist kein gültiges ISO-8601-Datum."}, status=400)

    connection, _ = McpConnection.objects.get_or_create(
        user=user, provider=McpConnection.Provider.SCALABLE,
        defaults={"mcp_server_url": MCP_PROVIDER_DEFAULTS[McpConnection.Provider.SCALABLE]},
    )
    _apply_token_import(
        connection,
        access_token=access_token,
        refresh_token=payload.get("refresh_token", "").strip(),
        client_id=payload.get("client_id", "").strip(),
        expires_at=expires_at,
    )

    logger.info(f"MCP-Token für {user} ({connection.provider}) per API-Push aktualisiert.")
    return JsonResponse({"ok": True, "provider": connection.provider, "is_connected": connection.is_connected})


@login_required
def mcp_scalable_login(request):
    """Startet den OAuth-Authorization-Code-Flow (mit PKCE) gegen den Scalable-MCP-Server."""
    connection = _get_or_create_connection(request, McpConnection.Provider.SCALABLE)
    redirect_uri = request.build_absolute_uri(reverse("core:mcp_callback"))

    flow = McpOAuthFlow(connection)
    try:
        flow.ensure_configured(redirect_uri, MCP_CLIENT_NAME)
        auth_url, pkce_state = flow.build_authorization_url(redirect_uri)
    except McpClientError as exc:
        logger.warning(f"MCP-Login (Scalable) fehlgeschlagen: {exc}")
        request.session["mcp_result"] = {"ok": False, "message": str(exc)}
        return redirect("core:mcp_scalable")

    request.session["mcp_oauth_flow"] = pkce_state
    return redirect(auth_url)


@login_required
def mcp_callback(request):
    """Gemeinsamer OAuth-Redirect-Endpoint für alle MCP-Provider (Provider steckt im Session-State)."""
    flow_state = request.session.pop("mcp_oauth_flow", None)

    if not flow_state:
        request.session["mcp_result"] = {"ok": False, "message": "Kein laufender Login-Vorgang gefunden."}
        return redirect("core:mcp_index")

    connection = get_object_or_404(McpConnection, id=flow_state["connection_id"], user=request.user)
    return_url = f"core:mcp_{connection.provider}"

    error = request.GET.get("error")
    if error:
        request.session["mcp_result"] = {"ok": False, "message": f"Login abgelehnt: {error}"}
        return redirect(return_url)

    if request.GET.get("state") != flow_state["state"]:
        request.session["mcp_result"] = {"ok": False, "message": "State-Mismatch — Login abgebrochen."}
        return redirect(return_url)

    code = request.GET.get("code")
    redirect_uri = request.build_absolute_uri(reverse("core:mcp_callback"))

    try:
        McpOAuthFlow(connection).exchange_code(code, redirect_uri, flow_state["code_verifier"])
        request.session["mcp_result"] = {"ok": True, "message": "Erfolgreich verbunden."}
    except McpClientError as exc:
        logger.warning(f"MCP-Token-Tausch fehlgeschlagen ({connection.provider}): {exc}")
        request.session["mcp_result"] = {"ok": False, "message": str(exc)}

    return redirect(return_url)


@login_required
@require_POST
def mcp_scalable_logout(request):
    """Trennt die Verbindung lokal (löscht die gespeicherten Tokens + Session-Verbindungsstatus)."""
    McpConnection.objects.filter(
        user=request.user, provider=McpConnection.Provider.SCALABLE,
    ).update(access_token_encrypted="", refresh_token_encrypted="", token_expires_at=None)
    request.session.pop("mcp_scalable_connected", None)
    return redirect("core:mcp_scalable")


@login_required
@require_POST
def mcp_scalable_command(request):
    """Führt ein Kommando gegen den Scalable-MCP-Server aus. Aktuell nur 'get_quote'."""
    connection = get_object_or_404(McpConnection, user=request.user, provider=McpConnection.Provider.SCALABLE)
    command = request.POST.get("command", "")
    isin = request.POST.get("isin", "").strip()

    if not _has_valid_token(connection):
        request.session["mcp_result"] = {"ok": False, "message": "Kein gültiger Token vorhanden — bitte zuerst verbinden."}
        return redirect("core:mcp_scalable")

    if command == "get_quote":
        if not isin:
            request.session["mcp_result"] = {"ok": False, "message": "ISIN darf nicht leer sein."}
        else:
            try:
                data = McpToolClient(connection).call_tool("get_security_quote", {"isin": isin})
                request.session["mcp_result"] = {"ok": True, "command": "get_quote", "isin": isin, "data": data}
            except McpClientError as exc:
                logger.warning(f"MCP-Tool-Call get_security_quote fehlgeschlagen: {exc}")
                request.session["mcp_result"] = {"ok": False, "message": str(exc)}
    else:
        request.session["mcp_result"] = {"ok": False, "message": f"Unbekanntes Kommando: {command!r}"}

    return redirect("core:mcp_scalable")
