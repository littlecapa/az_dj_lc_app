"""
MCP-Server (Model Context Protocol) — rein lesender Zugriff auf Portfolio-Daten für Claude.

POST /fintech/mcp

Transport: "Streamable HTTP", zustandslos — jede JSON-RPC-Anfrage wird direkt mit
application/json beantwortet, kein SSE-Stream, keine Sessions (GET/DELETE → 405).
Unterstützt: initialize, ping, tools/list, tools/call; Notifications → 202.

Authentifizierung: "Authorization: Bearer <MCP_READONLY_API_KEY>". Der Key gilt nur
hier, FINTECH_API_KEY und Admin-Session werden bewusst NICHT akzeptiert.

Die Tools rufen intern die bestehenden lesenden API-Views auf (fintech/apis/…), damit
die Logik nicht doppelt existiert. Es gibt ausschließlich lesende Tools.
"""

import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .cowork import PortfolioView, WatchlistView, AssetPriceHistoryView
from .fund_holdings_api import FundTopHoldingsView
from .securities import SecurityPriceView, SUPPORTED_TYPES
from .week52_api import Week52View, NewsListView

logger = logging.getLogger(__name__)

# Neueste zuerst; bei unbekannter Client-Version antworten wir mit der neuesten.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SERVER_INFO = {"name": "lc-app-portfolio", "title": "LC Portfolio (read-only)", "version": "1.0.0"}
INSTRUCTIONS = (
    "Read-only access to the owner's personal investment portfolio, watchlists and related "
    "market data. All monetary values are in EUR and returned as decimal strings. "
    "Prices are refreshed a few times per trading day, so they are not real-time "
    "unless you use get_live_price."
)

# JSON-RPC-Fehlercodes
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602

_ISIN = {"type": "string", "description": "ISIN, e.g. US21873S1087", "pattern": "^[A-Za-z]{2}[A-Za-z0-9]{10}$"}


class _McpReader:
    """Interner Principal für den Aufruf der lesenden Views — verlässt dieses Modul nie."""
    is_active = is_staff = is_authenticated = True
    username = "mcp-readonly"


def _call_view(view_cls, url_kwargs=None, query=None):
    request = HttpRequest()
    request.method = "GET"
    request.GET = QueryDict(mutable=True)
    for key, value in (query or {}).items():
        request.GET[key] = str(value)
    request.user = _McpReader()
    response = view_cls.as_view()(request, **(url_kwargs or {}))
    return response.status_code, json.loads(response.content)


def _watchlist(args):
    status, data = _call_view(WatchlistView)
    name = (args.get("watchlist") or "").strip().lower()
    if status == 200 and name:
        data["entries"] = [e for e in data["entries"] if e["watchlist"].lower() == name]
        data["count"] = len(data["entries"])
    return status, data


TOOLS = {
    "get_portfolio": {
        "title": "Portfolio",
        "description": "All current holdings with quantity, cost basis, current value, total and "
                       "1-day performance, plus a totals summary.",
        "inputSchema": {"type": "object", "properties": {}},
        "run": lambda a: _call_view(PortfolioView),
    },
    "get_watchlist": {
        "title": "Watchlists",
        "description": "Watchlist entries with price at entry, current price and performance since "
                       "entry, best performers first. Optionally filtered to one watchlist.",
        "inputSchema": {
            "type": "object",
            "properties": {"watchlist": {"type": "string", "description": "Watchlist name (case-insensitive); omit for all"}},
        },
        "run": _watchlist,
    },
    "get_price_history": {
        "title": "Price history",
        "description": "Stored EUR price history for one asset over the last N days, with first/last "
                       "price and change in percent.",
        "inputSchema": {
            "type": "object",
            "properties": {"isin": _ISIN, "days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30}},
            "required": ["isin"],
        },
        "run": lambda a: _call_view(AssetPriceHistoryView, {"isin": a["isin"]}, {"days": a.get("days", 30)}),
    },
    "get_52_week_range": {
        "title": "52-week range",
        "description": "52-week high and low in EUR for an asset that exists in the portfolio database.",
        "inputSchema": {"type": "object", "properties": {"isin": _ISIN}, "required": ["isin"]},
        "run": lambda a: _call_view(Week52View, {"isin": a["isin"]}),
    },
    "get_live_price": {
        "title": "Live price",
        "description": "Fetch the current EUR price for any ISIN live from the price providers "
                       "(slower than the stored prices).",
        "inputSchema": {
            "type": "object",
            "properties": {"isin": _ISIN, "type": {"type": "string", "enum": sorted(SUPPORTED_TYPES), "default": "STOCK"}},
            "required": ["isin"],
        },
        "run": lambda a: _call_view(SecurityPriceView, {"isin": a["isin"]}, {"type": a.get("type", "STOCK")}),
    },
    "get_news_events": {
        "title": "Portfolio news events",
        "description": "Portfolio alerts such as new 52-week highs/lows (max. 100), unread only by default.",
        "inputSchema": {
            "type": "object",
            "properties": {"unread_only": {"type": "boolean", "default": True}},
        },
        "run": lambda a: _call_view(NewsListView, query={"unread": "false" if a.get("unread_only") is False else "true"}),
    },
    "get_fund_top_holdings": {
        "title": "Fund top holdings",
        "description": "Top-10 holdings of an ETF or fund (source: JustETF).",
        "inputSchema": {"type": "object", "properties": {"isin": _ISIN}, "required": ["isin"]},
        "run": lambda a: _call_view(FundTopHoldingsView, {"fund_isin": a["isin"]}),
    },
}


def _tool_list():
    return [
        {
            "name": name,
            "title": t["title"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
        }
        for name, t in TOOLS.items()
    ]


class _RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _call_tool(params):
    name = params.get("name")
    args = params.get("arguments") or {}
    tool = TOOLS.get(name)
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


def _initialize(params):
    requested = params.get("protocolVersion")
    return {
        "protocolVersion": requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


METHODS = {
    "initialize": _initialize,
    "ping": lambda p: {},
    "tools/list": lambda p: {"tools": _tool_list()},
    "tools/call": _call_tool,
}


def _handle_message(msg):
    """Eine JSON-RPC-Nachricht verarbeiten. None = keine Antwort (Notification/Response)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Invalid JSON-RPC 2.0 message")
    if "method" not in msg or "id" not in msg:
        return None  # Notification (z.B. notifications/initialized) oder Client-Response
    msg_id, method = msg["id"], msg["method"]
    params = msg.get("params") or {}
    handler = METHODS.get(method)
    if handler is None:
        return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")
    if not isinstance(params, dict):
        return _error(msg_id, INVALID_PARAMS, "'params' must be an object")
    try:
        return {"jsonrpc": "2.0", "id": msg_id, "result": handler(params)}
    except _RpcError as exc:
        return _error(msg_id, exc.code, exc.message)


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _is_authorized(request) -> bool:
    expected = getattr(settings, "MCP_READONLY_API_KEY", None)
    auth = request.headers.get("Authorization", "")
    if not expected or not auth.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth[len("Bearer "):].strip().encode(), expected.encode())


@method_decorator(csrf_exempt, name="dispatch")
class McpView(View):
    http_method_names = ["post"]

    def post(self, request):
        if not _is_authorized(request):
            response = JsonResponse({"error": "Unauthorized"}, status=401)
            response["WWW-Authenticate"] = 'Bearer realm="lc-app-mcp"'
            return response

        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return JsonResponse(_error(None, PARSE_ERROR, "Parse error"), status=400)

        if isinstance(payload, list):  # JSON-RPC-Batch (Protokollversion 2025-03-26)
            replies = [r for r in (_handle_message(m) for m in payload) if r is not None]
            return JsonResponse(replies, safe=False) if replies else HttpResponse(status=202)

        reply = _handle_message(payload)
        return JsonResponse(reply) if reply is not None else HttpResponse(status=202)
