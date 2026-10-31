"""
Gemeinsamer Kern für die eigenen MCP-Server (Model Context Protocol) — rein lesende und eng begrenzte schreibende.

Transport: "Streamable HTTP", zustandslos — jede JSON-RPC-Anfrage wird direkt mit
application/json beantwortet, kein SSE-Stream, keine Sessions (GET/DELETE → 405).
Unterstützt: initialize, ping, tools/list, tools/call; Notifications → 202.

Authentifizierung: "Authorization: Bearer <Key>" — lesende Server (ReadOnlyMcpView) mit
MCP_READONLY_API_KEY, schreibende (WriteMcpView) ausschließlich mit MCP_WRITE_API_KEY. Die Keys
gelten nur für die MCP-Endpunkte, FINTECH_API_KEY und Admin-Session werden bewusst NICHT akzeptiert.

Ein konkreter Server ist eine Unterklasse von ReadOnlyMcpView bzw. WriteMcpView mit eigenen TOOLS,
SERVER_INFO und INSTRUCTIONS (siehe fintech.apis.mcp_server, leisure.mcp_server).
"""

import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# Neueste zuerst; bei unbekannter Client-Version antworten wir mit der neuesten.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

# JSON-RPC-Fehlercodes
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602


class _RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _is_authorized(request, key_setting) -> bool:
    expected = getattr(settings, key_setting, None)
    auth = request.headers.get("Authorization", "")
    if not expected or not auth.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth[len("Bearer "):].strip().encode(), expected.encode())


@method_decorator(csrf_exempt, name="dispatch")
class McpView(View):
    """TOOLS: {name: {title, description, inputSchema, run(args) -> (status, data)}}"""
    http_method_names = ["post"]
    API_KEY_SETTING = None
    READ_ONLY = True
    TOOLS = {}
    SERVER_INFO = {}
    INSTRUCTIONS = ""

    def post(self, request):
        if not _is_authorized(request, self.API_KEY_SETTING):
            response = JsonResponse({"error": "Unauthorized"}, status=401)
            response["WWW-Authenticate"] = 'Bearer realm="lc-app-mcp"'
            return response

        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return JsonResponse(_error(None, PARSE_ERROR, "Parse error"), status=400)

        if isinstance(payload, list):  # JSON-RPC-Batch (Protokollversion 2025-03-26)
            replies = [r for r in (self._handle_message(m) for m in payload) if r is not None]
            return JsonResponse(replies, safe=False) if replies else HttpResponse(status=202)

        reply = self._handle_message(payload)
        return JsonResponse(reply) if reply is not None else HttpResponse(status=202)

    def _handle_message(self, msg):
        """Eine JSON-RPC-Nachricht verarbeiten. None = keine Antwort (Notification/Response)."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _error(None, INVALID_REQUEST, "Invalid JSON-RPC 2.0 message")
        if "method" not in msg or "id" not in msg:
            return None  # Notification (z.B. notifications/initialized) oder Client-Response
        msg_id, method = msg["id"], msg["method"]
        params = msg.get("params") or {}
        handler = {
            "initialize": self._initialize,
            "ping": lambda p: {},
            "tools/list": lambda p: {"tools": self._tool_list()},
            "tools/call": self._call_tool,
        }.get(method)
        if handler is None:
            return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        if not isinstance(params, dict):
            return _error(msg_id, INVALID_PARAMS, "'params' must be an object")
        try:
            return {"jsonrpc": "2.0", "id": msg_id, "result": handler(params)}
        except _RpcError as exc:
            return _error(msg_id, exc.code, exc.message)

    def _initialize(self, params):
        requested = params.get("protocolVersion")
        return {
            "protocolVersion": requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": self.SERVER_INFO,
            "instructions": self.INSTRUCTIONS,
        }

    def _tool_list(self):
        return [
            {
                "name": name,
                "title": t["title"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
                "annotations": {"readOnlyHint": self.READ_ONLY, "openWorldHint": False},
            }
            for name, t in self.TOOLS.items()
        ]

    def _call_tool(self, params):
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = self.TOOLS.get(name)
        if tool is None:
            raise _RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        if not isinstance(args, dict):
            raise _RpcError(INVALID_PARAMS, "'arguments' must be an object")
        missing = [p for p in tool["inputSchema"].get("required", []) if not args.get(p)]
        if missing:
            raise _RpcError(INVALID_PARAMS, f"Missing required argument(s): {', '.join(missing)}")

        logger.info(f"MCP tools/call {name} {args}")
        try:
            status, data = tool["run"](args)
        except Exception as exc:
            logger.exception(f"MCP tool {name} failed")
            status, data = 500, {"error": "Internal Server Error", "detail": str(exc)}
        return {
            "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "structuredContent": data,
            "isError": status >= 400,
        }


class ReadOnlyMcpView(McpView):
    API_KEY_SETTING = "MCP_READONLY_API_KEY"


class WriteMcpView(McpView):
    """Für eng begrenzte Schreib-Tools (z. B. Vorschläge anlegen) — eigener Key, nie der Lese-Key."""
    API_KEY_SETTING = "MCP_WRITE_API_KEY"
    READ_ONLY = False
