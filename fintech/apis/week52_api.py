"""
52-Wochen-Range API

GET /fintech/api/assets/<isin>/week52
    Gibt das 52W-Hoch/Tief für eine ISIN zurück.
    Holt die Daten von Yahoo Finance wenn:
      - noch kein Eintrag in der DB vorhanden
      - der vorhandene Eintrag älter als 52 Wochen ist (→ wird gelöscht)
    Speichert den Wert anschließend in FiftyTwoWeekRange.

GET /fintech/api/news
    Gibt alle ungelesenen NewsEvents zurück.

POST /fintech/api/news/<id>/read
    Markiert ein NewsEvent als gelesen.

Authentication: X-Api-Key header OR active staff session.
"""

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from ..models import Asset, FiftyTwoWeekRange, NewsEvent
from .services.yahoo_finance import YahooFinanceRequest
from .services.comdirect_finance import ComdirectFinanceRequest
from .services.request_lib import KeyNotFoundWarning

logger = logging.getLogger(__name__)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
_yahoo  = YahooFinanceRequest()


def _is_authorized(request) -> bool:
    from django.conf import settings
    api_key = request.headers.get("X-Api-Key", "")
    if api_key and api_key == getattr(settings, "FINTECH_API_KEY", None):
        return True
    return request.user.is_authenticated and request.user.is_staff


# ---------------------------------------------------------------------------
# GET /fintech/api/assets/<isin>/week52
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class Week52View(View):

    http_method_names = ["get"]

    def get(self, request, isin: str):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        isin = isin.upper().strip()
        if not ISIN_RE.match(isin):
            return JsonResponse({"error": "Bad Request", "detail": f"'{isin}' is not a valid ISIN."}, status=400)

        try:
            asset = Asset.objects.get(isin=isin)
        except Asset.DoesNotExist:
            return JsonResponse({"error": "Not Found", "detail": f"Asset {isin} not in database."}, status=404)

        # Vorhandenen Eintrag prüfen
        try:
            r = asset.week52
            if r.is_expired():
                logger.info(f"52W range for {isin} expired — deleting and re-fetching")
                r.delete()
                r = None
        except FiftyTwoWeekRange.DoesNotExist:
            r = None

        # Bei Bedarf holen: Yahoo zuerst, Comdirect als Fallback
        if r is None:
            _comdirect = ComdirectFinanceRequest()
            data     = None
            provider = None

            # Versuch 1: Yahoo
            try:
                data     = _yahoo.isin2week52(isin)
                provider = "yahoo"
            except KeyNotFoundWarning as exc:
                logger.warning(f"Yahoo 52W not found for {isin}: {exc} — trying Comdirect")
            except Exception as exc:
                logger.error(f"Yahoo Finance 52W error for {isin}: {exc} — trying Comdirect")

            # Versuch 2: Comdirect
            if data is None:
                try:
                    data     = _comdirect.isin2week52(isin)
                    provider = "comdirect"
                except KeyNotFoundWarning as exc:
                    pass  # Beide Provider haben versagt → 404
                except Exception as exc:
                    logger.error(f"Comdirect 52W error for {isin}: {exc}")

            if data is None:
                return JsonResponse(
                    {"error": "Not Found", "detail": f"No 52W data found for {isin} (tried Yahoo + Comdirect)."},
                    status=404,
                )

            try:
                from fintech.libs.currency_utils import to_eur as _to_eur
                currency = data.get("currency", "EUR")
                high_eur = _to_eur(data["high"], currency)
                low_eur  = _to_eur(data["low"],  currency)
            except (InvalidOperation, KeyError, Exception) as exc:
                return JsonResponse({"error": "Parse/EUR-Umrechnung Error", "detail": str(exc)}, status=502)

            r = FiftyTwoWeekRange.objects.create(
                asset=asset,
                week52_high=high_eur,
                week52_high_date=None,
                week52_low=low_eur,
                week52_low_date=None,
                fetched_at=timezone.now(),
            )
            logger.info(f"52W range stored for {isin} via {provider}: H={high_eur} L={low_eur} EUR (orig {currency})")

        return JsonResponse({
            "isin":            isin,
            "week52_high":     str(r.week52_high),
            "week52_high_date": r.week52_high_date.isoformat() if r.week52_high_date else None,
            "week52_low":      str(r.week52_low),
            "week52_low_date": r.week52_low_date.isoformat() if r.week52_low_date else None,
            "fetched_at":      r.fetched_at.isoformat(),
        })


# ---------------------------------------------------------------------------
# GET  /fintech/api/news          → ungelesene Events
# POST /fintech/api/news/<id>/read → als gelesen markieren
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class NewsListView(View):

    http_method_names = ["get"]

    def get(self, request):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        only_unread = request.GET.get("unread", "true").lower() != "false"
        qs = NewsEvent.objects.prefetch_related("assets")
        if only_unread:
            qs = qs.filter(is_read=False)

        events = []
        for ev in qs[:100]:
            events.append({
                "id":         ev.id,
                "event_type": ev.event_type,
                "label":      ev.get_event_type_display(),
                "assets":     [
                    {"isin": a.isin, "symbol": a.symbol, "name": a.name}
                    for a in ev.assets.all()
                ],
                "old_value":  str(ev.old_value) if ev.old_value is not None else None,
                "new_value":  str(ev.new_value),
                "is_read":    ev.is_read,
                "created_at": ev.created_at.isoformat(),
            })

        return JsonResponse({"count": len(events), "events": events})


@method_decorator(csrf_exempt, name='dispatch')
class NewsMarkReadView(View):

    http_method_names = ["post"]

    def post(self, request, pk: int):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        updated = NewsEvent.objects.filter(pk=pk).update(is_read=True)
        if not updated:
            return JsonResponse({"error": "Not Found"}, status=404)
        return JsonResponse({"ok": True, "id": pk})
