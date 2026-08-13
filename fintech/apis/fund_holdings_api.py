"""
Fund-Holdings API — liefert per Web-Scraping (JustETF) die Top-10-Holdings
eines Fonds/ETF inkl. Gewichtung.

WICHTIG: JustETF zeigt kostenlos nur die 10 größten Positionen eines ETF.
Für verlässliche Werte jenseits der Top 10 bleibt das manuelle
FondHolding-Mapping (Django Admin) die Quelle.

Authentication: X-Api-Key header ODER aktive Staff-Session.

GET /fintech/api/funds/<fund_isin>/holdings/top10
    {"fund_isin": "...", "count": 10, "holdings": [{"isin", "name", "percentage"}, ...]}
"""
import logging
import re

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from .services.justetf import JustEtfRequest
from .services.soup_cache import SoupCache
from .services.request_lib import KeyNotFoundWarning

logger = logging.getLogger(__name__)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")

TOP10_NOTE = (
    "JustETF zeigt kostenlos nur die 10 größten Positionen eines ETF. "
    "Für verlässliche Werte jenseits der Top 10 das FondHolding-Mapping "
    "im Django-Admin manuell pflegen."
)

# One shared instance per process — hält den in-memory SoupCache
_soup_cache = SoupCache()
_justetf = JustEtfRequest(
    "https://www.justetf.com/de/etf-profile.html?isin={isin}",
    cache=_soup_cache,
    id="just_etf_holdings",
)


def _is_authorized(request) -> bool:
    api_key = getattr(settings, "FINTECH_API_KEY", None)
    if api_key and request.headers.get("X-Api-Key", "") == api_key:
        return True
    return request.user.is_active and request.user.is_staff


def _clean_isin(isin: str) -> str:
    return (isin or "").strip().upper()


class FundTopHoldingsView(View):
    """GET /fintech/api/funds/<fund_isin>/holdings/top10"""

    http_method_names = ["get"]

    def get(self, request, fund_isin: str):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        fund_isin = _clean_isin(fund_isin)
        if not ISIN_RE.match(fund_isin):
            return JsonResponse({"error": "Bad Request", "detail": f"'{fund_isin}' ist keine gültige ISIN."}, status=400)

        try:
            holdings = _justetf.get_top_holdings(fund_isin)
        except KeyNotFoundWarning:
            return JsonResponse(
                {"error": "Not Found", "detail": f"Kein ETF-Profil bei JustETF für {fund_isin} gefunden."},
                status=404,
            )
        except Exception as exc:
            logger.exception(f"JustETF-Holdings-Abruf für {fund_isin} fehlgeschlagen")
            return JsonResponse({"error": "Internal Server Error", "detail": str(exc)}, status=500)

        return JsonResponse({
            "fund_isin": fund_isin,
            "source": "justetf_top10",
            "count": len(holdings),
            "holdings": [
                {"isin": h["isin"], "name": h["name"], "percentage": str(h["percentage"])}
                for h in holdings
            ],
            "note": TOP10_NOTE,
        })
