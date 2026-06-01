"""
Asset REST API

POST /fintech/api/assets/<isin>/resolve-name
    Schlägt den Namen für eine ISIN bei Yahoo Finance nach und
    aktualisiert das Asset-Record falls der Name noch nicht gesetzt ist
    (d.h. name == isin) oder force=true übergeben wird.

POST /fintech/api/assets/resolve-names
    Bulk-Version: aktualisiert alle Assets deren name == isin.
    Optional: {"force": true} aktualisiert alle Assets unabhängig vom Namen.

Authentication: X-Api-Key header OR active staff session.
"""

import logging
import json
import re

from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from ..models import Asset
from .services.yahoo_finance import YahooFinanceRequest
from .services.request_lib import KeyNotFoundWarning

logger = logging.getLogger(__name__)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
_yahoo  = YahooFinanceRequest()


def _is_authorized(request) -> bool:
    api_key = getattr(settings, "FINTECH_API_KEY", None)
    if api_key and request.headers.get("X-Api-Key", "") == api_key:
        return True
    return request.user.is_active and request.user.is_staff


# ---------------------------------------------------------------------------
# POST /fintech/api/assets/<isin>/resolve-name
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class AssetResolveNameView(View):
    """Look up name from Yahoo Finance and update asset record."""

    http_method_names = ["post"]

    def post(self, request, isin: str):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        isin = isin.upper().strip()
        if not ISIN_RE.match(isin):
            return JsonResponse(
                {"error": "Bad Request", "detail": f"'{isin}' is not a valid ISIN."}, status=400
            )

        try:
            data  = json.loads(request.body or "{}")
            force = bool(data.get("force", False))
        except json.JSONDecodeError:
            force = False

        try:
            asset = Asset.objects.get(isin=isin)
        except Asset.DoesNotExist:
            return JsonResponse(
                {"error": "Not Found", "detail": f"Asset {isin} not in database."}, status=404
            )

        if asset.name != isin and not force:
            return JsonResponse({
                "isin":    isin,
                "name":    asset.name,
                "updated": False,
                "detail":  "Name already set. Pass force=true to overwrite.",
            })

        try:
            new_name = _yahoo.isin2name(isin)
        except (KeyNotFoundWarning, Exception) as exc:
            return JsonResponse(
                {"error": "Not Found", "detail": f"Yahoo Finance lookup failed: {exc}"}, status=404
            )

        old_name = asset.name
        asset.name = new_name
        asset.save(update_fields=["name"])
        logger.info(f"Asset name updated: {isin} '{old_name}' → '{new_name}'")

        return JsonResponse({
            "isin":     isin,
            "old_name": old_name,
            "name":     new_name,
            "updated":  True,
        })


# ---------------------------------------------------------------------------
# POST /fintech/api/assets/resolve-names  (Bulk)
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class AssetResolveNamesView(View):
    """
    Bulk: resolve names for all assets where name == isin (or all with force=true).
    Returns per-asset results.
    """

    http_method_names = ["post"]

    def post(self, request):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        try:
            data  = json.loads(request.body or "{}")
            force = bool(data.get("force", False))
        except json.JSONDecodeError:
            force = False

        if force:
            assets = list(Asset.objects.all())
        else:
            # Nur Assets wo Name == ISIN (d.h. noch kein richtiger Name gesetzt)
            assets = [a for a in Asset.objects.all() if a.name == a.isin]

        if not assets:
            return JsonResponse({"message": "Keine Assets zum Aktualisieren gefunden.", "updated": 0, "failed": 0, "details": []})

        updated = failed = 0
        details = []

        for asset in assets:
            try:
                new_name = _yahoo.isin2name(asset.isin)
                old_name = asset.name
                asset.name = new_name
                asset.save(update_fields=["name"])
                updated += 1
                details.append({"isin": asset.isin, "old_name": old_name, "name": new_name, "status": "updated"})
                logger.info(f"Bulk resolve: {asset.isin} '{old_name}' → '{new_name}'")
            except (KeyNotFoundWarning, Exception) as exc:
                failed += 1
                details.append({"isin": asset.isin, "name": asset.name, "status": "failed", "error": str(exc)})
                logger.warning(f"Bulk resolve failed for {asset.isin}: {exc}")

        return JsonResponse({
            "total":   len(assets),
            "updated": updated,
            "failed":  failed,
            "details": details,
        }, status=207 if failed else 200)
