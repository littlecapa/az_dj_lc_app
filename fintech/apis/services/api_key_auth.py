"""
API Key authentication middleware for the fintech REST API.

The key is read from settings.FINTECH_API_KEY (injected via GitHub Actions Secret
→ Azure App Service environment variable).

Usage in settings.py:
    MIDDLEWARE = [
        ...
        "fintech.middleware.api_key_auth.ApiKeyMiddleware",
    ]
    FINTECH_API_KEY = env("FINTECH_API_KEY")   # e.g. via django-environ
"""

import logging
from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)

# Only protect routes under this prefix
PROTECTED_PREFIX = "/fintech/"

class ApiKeyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._api_key = getattr(settings, "FINTECH_API_KEY", None)
        if not self._api_key:
            logger.warning("FINTECH_API_KEY is not set — API endpoints are unprotected!")

    def __call__(self, request):
        if request.path.startswith(PROTECTED_PREFIX):
            if not self._is_authenticated(request):
                return JsonResponse(
                    {"error": "Unauthorized", "detail": "Valid X-API-Key header required."},
                    status=401,
                )
        return self.get_response(request)

    def _is_authenticated(self, request) -> bool:
        if not self._api_key:
            return False  # fail-closed when key is not configured
        provided = request.headers.get("X-Api-Key", "")
        return provided == self._api_key
