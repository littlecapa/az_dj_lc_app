"""
Cowork API — read-only endpoints for Claude (and other API clients).

Authentication: X-Api-Key header  OR  ?api_key=... query param  OR  active staff session.
The query-param form exists because some fetch tools (e.g. Claude's WebFetch) cannot
send custom headers. Since every endpoint here is GET-only/read-only, accepting the
key via query string is an acceptable trade-off (it may end up in server access logs —
avoid using it for anything more sensitive than this read-only reporting use case).
All responses are application/json.

Endpoints
---------
GET /fintech/api/portfolio
    All holdings with current value, cost basis, P&L and daily delta.
    Includes a totals summary at the top level.

GET /fintech/api/watchlist
    All watchlist entries ordered by performance since entry.

GET /fintech/api/assets/<isin>/history?days=30
    Price history for one ISIN (default 30 days, max 365).
"""

import logging
import re
from decimal import Decimal
from typing import Optional
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.db.models import F, ExpressionWrapper, DecimalField
from django.db.models.functions import NullIf
from django.utils import timezone
from datetime import timedelta

from ..model_views import PortfolioSummary
from ..models import WatchlistEntry, Price

logger = logging.getLogger(__name__)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
D = DecimalField(max_digits=20, decimal_places=4)


def _is_authorized(request) -> bool:
    api_key = getattr(settings, "FINTECH_API_KEY", None)
    if api_key and request.headers.get("X-Api-Key", "") == api_key:
        return True
    if api_key and request.GET.get("api_key", "") == api_key:
        return True
    return request.user.is_active and request.user.is_staff


def _dec(value) -> Optional[str]:
    """Serialize Decimal/float to string, None stays None."""
    if value is None:
        return None
    return str(value)


# ---------------------------------------------------------------------------
# GET /fintech/api/portfolio
# ---------------------------------------------------------------------------

class PortfolioView(View):
    """Return all holdings as JSON, sorted by yesterday's daily delta (desc)."""

    http_method_names = ["get"]

    def get(self, request):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        rows = list(PortfolioSummary.objects.portfolio())

        total_invested     = Decimal(0)
        total_current      = Decimal(0)

        positions = []
        for r in rows:
            invested = r.get("purchase_price") or Decimal(0)
            current  = r.get("current_value")  or Decimal(0)
            total_invested += invested
            total_current  += current

            positions.append({
                "isin":              r["isin"],
                "name":              r["name"],
                "asset_class":       r["asset_class"],
                "quantity":          _dec(r.get("total_quantity")),
                "purchase_price":    _dec(r.get("purchase_price")),
                "current_value":     _dec(r.get("current_value")),
                "delta_abs":         _dec(r.get("delta_abs")),
                "delta_perc":        _dec(r.get("delta_perc")),
                "delta_perc_1d":     _dec(r.get("delta_perc_yesterday")),
                "not_for_sale":      r.get("holdings__not_for_sale"),
                "stake_recovered":   r.get("holdings__stake_recovered"),
            })

        total_delta_abs  = total_current - total_invested
        total_delta_perc = (
            (total_current / total_invested - 1) * 100
            if total_invested else None
        )

        return JsonResponse({
            "summary": {
                "total_invested":    _dec(total_invested),
                "total_current":     _dec(total_current),
                "total_delta_abs":   _dec(total_delta_abs),
                "total_delta_perc":  _dec(total_delta_perc),
                "position_count":    len(positions),
            },
            "positions": positions,
        })


# ---------------------------------------------------------------------------
# GET /fintech/api/watchlist
# ---------------------------------------------------------------------------

class WatchlistView(View):
    """Return all watchlist entries as JSON, best performers first."""

    http_method_names = ["get"]

    def get(self, request):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        entries = (
            WatchlistEntry.objects
            .select_related("asset", "watchlist")
            .annotate(
                delta_perc_since_add=ExpressionWrapper(
                    (
                        F("asset__current_price")
                        / NullIf(F("price_at_add"), Decimal("0"))
                        - Decimal("1")
                    ) * Decimal("100"),
                    output_field=D,
                )
            )
            .order_by(F("delta_perc_since_add").desc(nulls_last=True))
            .values(
                "watchlist__name",
                "asset__isin",
                "asset__name",
                "asset__asset_class",
                "asset__current_price",
                "asset__current_price_timestamp",
                "price_at_add",
                "added_at",
                "source",
                "notes",
                "delta_perc_since_add",
            )
        )

        data = [
            {
                "watchlist":           e["watchlist__name"],
                "isin":                e["asset__isin"],
                "name":                e["asset__name"],
                "asset_class":         e["asset__asset_class"],
                "current_price":       _dec(e["asset__current_price"]),
                "price_at_add":        _dec(e["price_at_add"]),
                "delta_perc_since_add": _dec(e["delta_perc_since_add"]),
                "added_at":            e["added_at"].isoformat() if e["added_at"] else None,
                "price_timestamp":     e["asset__current_price_timestamp"].isoformat() if e["asset__current_price_timestamp"] else None,
                "source":              e["source"],
                "notes":               e["notes"],
            }
            for e in entries
        ]

        return JsonResponse({"count": len(data), "entries": data})


# ---------------------------------------------------------------------------
# GET /fintech/api/assets/<isin>/history?days=30
# ---------------------------------------------------------------------------

class AssetPriceHistoryView(View):
    """Return stored price history for one ISIN."""

    http_method_names = ["get"]
    MAX_DAYS = 365
    DEFAULT_DAYS = 30

    def get(self, request, isin: str):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        isin = isin.upper().strip()
        if not ISIN_RE.match(isin):
            return JsonResponse(
                {"error": "Bad Request", "detail": f"'{isin}' is not a valid ISIN."},
                status=400,
            )

        try:
            days = int(request.GET.get("days", self.DEFAULT_DAYS))
            if not (1 <= days <= self.MAX_DAYS):
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse(
                {"error": "Bad Request", "detail": f"'days' must be an integer between 1 and {self.MAX_DAYS}."},
                status=400,
            )

        since = timezone.now() - timedelta(days=days)
        qs = (
            Price.objects
            .filter(asset_id=isin, timestamp__gte=since)
            .order_by("timestamp")
            .values("timestamp", "current_price")
        )

        history = [
            {"timestamp": p["timestamp"].isoformat(), "price": _dec(p["current_price"])}
            for p in qs
        ]

        if not history:
            # Return empty result — not a 404, the ISIN may simply have no history yet
            return JsonResponse({"isin": isin, "days": days, "count": 0, "history": []})

        prices = [p["current_price"] for p in qs]  # already evaluated above via list comp

        # Re-query for stats to avoid holding two copies of a potentially large list
        first_price = Decimal(history[0]["price"])
        last_price  = Decimal(history[-1]["price"])
        delta_perc  = (last_price / first_price - 1) * 100 if first_price else None

        return JsonResponse({
            "isin":        isin,
            "days":        days,
            "count":       len(history),
            "first_price": _dec(first_price),
            "last_price":  _dec(last_price),
            "delta_perc":  _dec(delta_perc),
            "history":     history,
        })
