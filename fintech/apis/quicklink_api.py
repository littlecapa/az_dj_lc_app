"""
QuickLink Import API

POST /fintech/api/quicklinks/import
    Bulk-Import von Quick Links. Akzeptiert ein JSON-Array.
    Bestehende Links (gleicher Name + Kategorie) werden aktualisiert.

Authentication: X-Api-Key header OR active staff session.
"""

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from homepage.models import QuickLink

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {c for c, _ in QuickLink.Category.choices}


def _is_authorized(request) -> bool:
    api_key = getattr(settings, "FINTECH_API_KEY", None)
    if api_key and request.headers.get("X-Api-Key", "") == api_key:
        return True
    return request.user.is_active and request.user.is_staff


@method_decorator(csrf_exempt, name='dispatch')
class QuickLinkImportView(View):
    """
    Bulk-Import Quick Links.

    Body: JSON-Array von Objekten:
      [
        {"name": "Chess.com",  "url": "https://chess.com",  "prio": 1, "category": "Chess"},
        {"name": "Tagesschau", "url": "https://tagesschau.de", "prio": 2, "category": "News"}
      ]

    Felder:
      name      (required)  String, max 32 Zeichen
      url       (required)  URL
      category  (required)  Chess | Finance | AI | Video | News | Misc | Travel | Bonn
      prio      (optional)  Integer >= 1, Default 2
      is_active (optional)  Boolean, Default true
    """

    http_method_names = ["post"]

    def post(self, request):
        if not _is_authorized(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        try:
            items = json.loads(request.body or "[]")
            if not isinstance(items, list):
                raise ValueError("Expected a JSON array [ ... ]")
        except (json.JSONDecodeError, ValueError) as exc:
            return JsonResponse({"error": "Bad Request", "detail": str(exc)}, status=400)

        created = updated = 0
        errors = []
        details = []

        for idx, item in enumerate(items, start=1):
            name     = str(item.get("name", "")).strip()
            url      = str(item.get("url",  "")).strip()
            category = str(item.get("category", "")).strip()
            prio     = item.get("prio", 2)
            is_active = item.get("is_active", True)

            # Validierung
            if not name:
                errors.append(f"Item {idx}: 'name' is required.")
                continue
            if len(name) > 32:
                errors.append(f"Item {idx}: 'name' max 32 chars (got {len(name)}).")
                continue
            if not url:
                errors.append(f"Item {idx} ({name}): 'url' is required.")
                continue
            if category not in VALID_CATEGORIES:
                errors.append(f"Item {idx} ({name}): unknown category '{category}'. Valid: {sorted(VALID_CATEGORIES)}")
                continue
            try:
                prio = int(prio)
                if prio < 1:
                    raise ValueError
            except (ValueError, TypeError):
                errors.append(f"Item {idx} ({name}): 'prio' must be an integer >= 1.")
                continue

            obj, was_created = QuickLink.objects.update_or_create(
                name=name,
                category=category,
                defaults={
                    "url":       url,
                    "prio":      prio,
                    "is_active": bool(is_active),
                },
            )

            if was_created:
                created += 1
            else:
                updated += 1

            details.append({
                "name":     name,
                "category": category,
                "status":   "created" if was_created else "updated",
            })
            logger.info(f"QuickLink {'created' if was_created else 'updated'}: [{category}] {name}")

        return JsonResponse({
            "total":   len(items),
            "created": created,
            "updated": updated,
            "errors":  errors,
            "details": details,
        }, status=207 if errors else 200)
