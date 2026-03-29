"""
GET /fintech/securities/{isin}/price?type=Stock|ETF|Certificate
 
Returns:
    200  {"isin": "...", "price_eur": "12.34", "type": "Stock"}
    400  {"error": "...", "detail": "..."}
    404  {"error": "Not Found", "detail": "Price could not be retrieved for ISIN ..."}
    500  {"error": "Internal Server Error", "detail": "..."}
 
Authentication: X-API-Key header (handled by ApiKeyMiddleware).
"""
 
import logging
import re
from decimal import Decimal
 
from django.http import JsonResponse
from django.views import View
 
from .services.provider_manager import ProviderManager
 
logger = logging.getLogger(__name__)
 
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
VALID_TYPES = {"Stock", "ETF", "Certificate"}
 
# One shared instance per process — holds the in-memory SoupCache
_provider_manager = ProviderManager()
 
 
class SecurityPriceView(View):
    """Return the current EUR price for a given ISIN."""
 
    http_method_names = ["get"]
 
    def get(self, request, isin: str):
        isin = isin.upper().strip()
 
        # --- validate ISIN ---
        if not ISIN_RE.match(isin):
            return JsonResponse(
                {"error": "Bad Request", "detail": f"'{isin}' is not a valid ISIN."},
                status=400,
            )
 
        # --- validate type ---
        security_type = request.GET.get("type", "Stock")
        if security_type not in VALID_TYPES:
            return JsonResponse(
                {
                    "error": "Bad Request",
                    "detail": f"Query param 'type' must be one of {sorted(VALID_TYPES)}.",
                },
                status=400,
            )
 
        # --- fetch price ---
        try:
            price: Decimal | None = _provider_manager.isin2price(isin, security_type)
        except ValueError as exc:
            return JsonResponse({"error": "Bad Request", "detail": str(exc)}, status=400)
        except Exception as exc:
            logger.exception(f"Unexpected error fetching price for {isin}")
            return JsonResponse(
                {"error": "Internal Server Error", "detail": str(exc)}, status=500
            )
 
        if price is None:
            return JsonResponse(
                {
                    "error": "Not Found",
                    "detail": f"Price could not be retrieved for ISIN {isin}.",
                },
                status=404,
            )
 
        return JsonResponse(
            {
                "isin": isin,
                "type": security_type,
                "price_eur": str(round(price, 4)),
                "currency": "EUR",
            }
        )
 