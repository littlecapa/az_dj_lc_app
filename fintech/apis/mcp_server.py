"""
MCP-Server (Model Context Protocol) — rein lesender Zugriff auf Portfolio-Daten für Claude.

POST /fintech/mcp

Transport, JSON-RPC und Authentifizierung (Bearer MCP_READONLY_API_KEY): core.mcp_server.

Die Tools rufen intern die bestehenden lesenden API-Views auf (fintech/apis/…), damit
die Logik nicht doppelt existiert. Es gibt ausschließlich lesende Tools.
"""

import json

from django.http import HttpRequest, QueryDict

from core.mcp_server import ReadOnlyMcpView

from .cowork import PortfolioView, WatchlistView, AssetPriceHistoryView
from .fund_holdings_api import FundTopHoldingsView
from .securities import SecurityPriceView, SUPPORTED_TYPES
from .week52_api import Week52View, NewsListView

SERVER_INFO = {"name": "lc-app-portfolio", "title": "LC Portfolio (read-only)", "version": "1.0.0"}
INSTRUCTIONS = (
    "Read-only access to the owner's personal investment portfolio, watchlists and related "
    "market data. All monetary values are in EUR and returned as decimal strings. "
    "Prices are refreshed a few times per trading day, so they are not real-time "
    "unless you use get_live_price."
)

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


class McpView(ReadOnlyMcpView):
    TOOLS = TOOLS
    SERVER_INFO = SERVER_INFO
    INSTRUCTIONS = INSTRUCTIONS
