"""
Watchlist REST API

POST   /fintech/api/watchlist/create
    Watchlist anlegen (oder bestehende zurückgeben)

POST   /fintech/api/watchlist/<name>/entries
    Asset zu einer Watchlist hinzufügen.
    Legt das Asset an falls noch nicht vorhanden.
    Holt aktiv einen aktuellen Kurs wenn keiner gecacht ist.

DELETE /fintech/api/watchlist/<name>/entries/<isin>
    Einzelnen Eintrag aus einer Watchlist entfernen.
    Das Asset selbst bleibt erhalten.

DELETE /fintech/api/watchlist/<name>
    Gesamte Watchlist inkl. aller Einträge löschen.

Authentication: X-Api-Key header OR active staff session.
"""

import json
import logging
import re
from decimal import Decimal
from typing import Optional, Tuple

from django.conf import settings
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from ..models import Asset, Watchlist, WatchlistEntry
from ..models_helper.asset_class import AssetClass
from .services.provider_manager import ProviderManager
from .services.yahoo_finance import YahooFinanceRequest
from .services.request_lib import KeyNotFoundWarning

logger = logging.getLogger(__name__)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")

# One shared instance per process
_provider_manager = ProviderManager()
_yahoo            = YahooFinanceRequest()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _is_authorized(request) -> bool:
    api_key = getattr(settings, "FINTECH_API_KEY", None)
    if api_key and request.headers.get("X-Api-Key", "") == api_key:
        return True
    return request.user.is_active and request.user.is_staff


def _resolve_user(request) -> User:
    """Return the acting user: session user if available, else first superuser."""
    if request.user.is_authenticated and request.user.is_staff:
        return request.user
    return User.objects.filter(is_superuser=True).order_by('id').first()


def _json_body(request) -> Tuple[dict, Optional[str]]:
    """Parse JSON body. Returns (data, error_message)."""
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError as exc:
        return {}, f"Invalid JSON: {exc}"


# ---------------------------------------------------------------------------
# POST /fintech/api/watchlist
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class WatchlistCreateView(View):
    """Create a new watchlist or return existing one with the same name."""

    http_method_names = ["post"]

    def post(self, request):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        data, err = _json_body(request)
        if err:
            return JsonResponse({"error": "Bad Request", "detail": err}, status=400)

        name = str(data.get("name", "")).strip()
        if not name:
            return JsonResponse(
                {"error": "Bad Request", "detail": "'name' is required."}, status=400
            )
        if len(name) > 100:
            return JsonResponse(
                {"error": "Bad Request", "detail": "'name' must be ≤ 100 characters."}, status=400
            )

        user = _resolve_user(request)
        if user is None:
            return JsonResponse({"error": "Internal Server Error", "detail": "No staff user found."}, status=500)

        watchlist, created = Watchlist.objects.get_or_create(
            name=name, user=user
        )

        return JsonResponse({
            "watchlist": watchlist.name,
            "created":   created,
            "owner":     user.username,
            "entry_count": watchlist.entries.count(),
        }, status=201 if created else 200)


# ---------------------------------------------------------------------------
# POST /fintech/api/watchlist/<name>/entries
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class WatchlistEntryCreateView(View):
    """Add an asset to a watchlist. Creates asset if unknown. Fetches price if missing."""

    http_method_names = ["post"]

    def post(self, request, watchlist_name: str):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        data, err = _json_body(request)
        if err:
            return JsonResponse({"error": "Bad Request", "detail": err}, status=400)

        # --- ISIN ---
        isin = str(data.get("isin", "")).strip().upper()
        if not ISIN_RE.match(isin):
            return JsonResponse(
                {"error": "Bad Request", "detail": f"'{isin}' is not a valid ISIN."}, status=400
            )

        # --- asset_class ---
        asset_class = str(data.get("asset_class", AssetClass.STOCK)).strip().upper()
        if not AssetClass.is_valid(asset_class):
            return JsonResponse(
                {"error": "Bad Request", "detail": f"Unknown asset_class '{asset_class}'. Valid: {list(AssetClass.values)}"}, status=400
            )

        user = _resolve_user(request)
        if user is None:
            return JsonResponse({"error": "Internal Server Error", "detail": "No staff user found."}, status=500)

        # --- Watchlist ermitteln ---
        try:
            watchlist = Watchlist.objects.get(name=watchlist_name, user=user)
        except Watchlist.DoesNotExist:
            # Watchlist on-the-fly anlegen
            watchlist = Watchlist.objects.create(name=watchlist_name, user=user)
            logger.info(f"Watchlist '{watchlist_name}' wurde neu angelegt für {user.username}")

        # --- Asset anlegen oder holen ---
        asset_name = str(data.get("name", "")).strip() or isin
        asset, asset_created = Asset.objects.get_or_create(
            isin=isin,
            defaults={"name": asset_name, "asset_class": asset_class},
        )
        if asset_created:
            logger.info(f"Neues Asset angelegt: {isin} ({asset_name})")

        # --- Namen auflösen falls noch nicht gesetzt ---
        if asset.name == isin:
            try:
                real_name = _yahoo.isin2name(isin)
                asset.name = real_name
                asset.save(update_fields=["name"])
                logger.info(f"Asset-Name aufgelöst: {isin} → '{real_name}'")
            except Exception as exc:
                logger.warning(f"Name-Auflösung für {isin} fehlgeschlagen: {exc}")

        # --- Kurs sicherstellen ---
        price_fetched = False
        if asset.current_price is None:
            logger.info(f"Kein Kurs für {isin} — hole aktiv via ProviderManager")
            try:
                price = _provider_manager.isin2price(isin, asset.asset_class)
                if price is not None:
                    from ..models import Price
                    from django.utils import timezone
                    Price.objects.create(
                        asset=asset,
                        current_price=price,
                        timestamp=timezone.now(),
                    )
                    asset.refresh_from_db()
                    price_fetched = True
                    logger.info(f"Kurs für {isin} geholt: {price}")
            except Exception as exc:
                logger.warning(f"Kurs-Abruf für {isin} fehlgeschlagen: {exc}")

        # --- Watchlist-Entry anlegen oder aktualisieren ---
        source = str(data.get("source", "")).strip()
        notes  = str(data.get("notes",  "")).strip()

        existing = WatchlistEntry.objects.filter(watchlist=watchlist, asset=asset).first()
        if existing:
            existing.source = source or existing.source
            existing.notes  = notes  or existing.notes
            existing.save(update_fields=["source", "notes"])
            entry_created = False
            entry = existing
        else:
            entry = WatchlistEntry(
                watchlist=watchlist,
                asset=asset,
                source=source,
                notes=notes,
            )
            entry.save()  # price_at_add wird in save() aus asset.current_price gesetzt
            entry_created = True

        return JsonResponse({
            "watchlist":     watchlist.name,
            "isin":          isin,
            "name":          asset.name,
            "asset_class":   asset.asset_class,
            "price_at_add":  str(entry.price_at_add) if entry.price_at_add else None,
            "price_fetched": price_fetched,
            "entry_created": entry_created,
            "asset_created": asset_created,
        }, status=201 if entry_created else 200)


# ---------------------------------------------------------------------------
# DELETE /fintech/api/watchlist/<name>/entries/<isin>
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class WatchlistEntryDeleteView(View):
    """
    Remove a single asset from a watchlist.

    The asset record itself is NOT deleted — only the watchlist entry.
    Returns 404 if the watchlist or entry does not exist.
    """

    http_method_names = ["delete"]

    def delete(self, request, watchlist_name: str, isin: str):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        isin = isin.upper().strip()
        if not ISIN_RE.match(isin):
            return JsonResponse(
                {"error": "Bad Request", "detail": f"'{isin}' is not a valid ISIN."}, status=400
            )

        user = _resolve_user(request)

        try:
            watchlist = Watchlist.objects.get(name=watchlist_name, user=user)
        except Watchlist.DoesNotExist:
            return JsonResponse(
                {"error": "Not Found", "detail": f"Watchlist '{watchlist_name}' not found."}, status=404
            )

        deleted, _ = WatchlistEntry.objects.filter(
            watchlist=watchlist, asset_id=isin
        ).delete()

        if not deleted:
            return JsonResponse(
                {"error": "Not Found", "detail": f"ISIN '{isin}' not in watchlist '{watchlist_name}'."}, status=404
            )

        logger.info(f"WatchlistEntry gelöscht: {isin} aus '{watchlist_name}'")
        return JsonResponse({
            "deleted":        True,
            "watchlist":      watchlist_name,
            "isin":           isin,
            "entries_left":   watchlist.entries.count(),
        })


# ---------------------------------------------------------------------------
# DELETE /fintech/api/watchlist/<name>
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class WatchlistDeleteView(View):
    """
    Delete an entire watchlist including all its entries.

    Assets are NOT deleted. Returns 404 if the watchlist does not exist.
    """

    http_method_names = ["delete"]

    def delete(self, request, watchlist_name: str):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        user = _resolve_user(request)

        try:
            watchlist = Watchlist.objects.get(name=watchlist_name, user=user)
        except Watchlist.DoesNotExist:
            return JsonResponse(
                {"error": "Not Found", "detail": f"Watchlist '{watchlist_name}' not found."}, status=404
            )

        entry_count = watchlist.entries.count()
        watchlist.delete()

        logger.info(f"Watchlist gelöscht: '{watchlist_name}' ({entry_count} Einträge)")
        return JsonResponse({
            "deleted":      True,
            "watchlist":    watchlist_name,
            "entries_removed": entry_count,
        })
