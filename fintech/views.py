from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from django.db.models import F, ExpressionWrapper, DecimalField
from django.db.models.functions import NullIf
from .model_views import PortfolioSummary
from .models import WatchlistEntry, Watchlist, Asset
import json
from decimal import Decimal
from .apis.services.csv_import import import_transactions
from django.contrib import messages
from django.core.management import call_command
from django.views.decorators.cache import never_cache

import logging

logger = logging.getLogger(__name__)

def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def _is_api_key_valid(request) -> bool:
    api_key = getattr(settings, "FINTECH_API_KEY", None)
    if not api_key:
        return False
    return request.headers.get("X-Api-Key", "") == api_key

def portfolio_export(request):
    if not (_is_api_key_valid(request) or (request.user.is_active and request.user.is_staff)):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = list(PortfolioSummary.objects.portfolio())
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=decimal_serializer)
    return render(request, "fintech/portfolio_export.html", {"json_str": json_str})


def watchlist_export(request):
    if not (_is_api_key_valid(request) or (request.user.is_active and request.user.is_staff)):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    D = DecimalField(max_digits=10, decimal_places=4)

    entries = (
        WatchlistEntry.objects
        .select_related('asset', 'watchlist')
        .annotate(
            delta_perc_since_add=ExpressionWrapper(
                (
                    F('asset__current_price')
                    / NullIf(F('price_at_add'), Decimal('0'))
                    - Decimal('1')
                ) * Decimal('100'),
                output_field=D,
            )
        )
        .order_by(F('delta_perc_since_add').desc(nulls_last=True))
        .values(
            'watchlist__name',
            'asset__isin',
            'asset__name',
            'asset__asset_class',
            'asset__current_price',
            'asset__current_price_timestamp',
            'price_at_add',
            'added_at',
            'source',
            'notes',
            'delta_perc_since_add',
        )
    )

    data = list(entries)
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=decimal_serializer)
    return render(request, "fintech/portfolio_export.html", {"json_str": json_str})

@never_cache
@staff_member_required
def portfolio_import(request):
    call_command("update_prices")  # Preise vor Import aktualisieren, damit sie in der UI direkt sichtbar sind
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        dry_run  = request.POST.get("dry_run") == "on"

        if not csv_file:
            request.session["import_error"] = "Bitte eine CSV-Datei auswählen."
            return redirect("fintech:portfolio-import")

        if not csv_file.name.endswith(".csv"):
            request.session["import_error"] = "Nur CSV-Dateien werden unterstützt."
            return redirect("fintech:portfolio-import")

        try:
            content = csv_file.read().decode("utf-8")
        except UnicodeDecodeError:
            content = csv_file.read().decode("latin-1")

        result = import_transactions(content, dry_run=dry_run)

        request.session["import_result"] = {
            "total":    result.total,
            "imported": result.imported,
            "skipped":  result.skipped,
            "errors":   result.errors,
            "dry_run":  result.dry_run,
        }
        return redirect("fintech:portfolio-import")

    result_data = request.session.pop("import_result", None)
    error       = request.session.pop("import_error", None)
    return render(request, "fintech/portfolio_import.html", {
        "result": result_data,
        "error":  error,
    })


_WATCHLIST_IMPORT_EXAMPLE = json.dumps([
    {
        "watchlist": "Tech Favoriten",
        "isin": "US0378331005",
        "source": "Handelsblatt 2026-05-27",
        "notes": "Starkes Q1, KGV noch attraktiv"
    },
    {
        "watchlist": "Tech Favoriten",
        "isin": "DE000SAP0011",
        "source": "",
        "notes": "Auf Einstiegsniveau beobachten"
    }
], indent=2, ensure_ascii=False)


@never_cache
@staff_member_required
def watchlist_import(request):
    if request.method != "POST":
        return render(request, "fintech/watchlist_import.html", {
            "example_json": _WATCHLIST_IMPORT_EXAMPLE,
            "submitted_json": "",
            "dry_run": True,
        })

    raw = request.POST.get("json_data", "").strip()
    dry_run = request.POST.get("dry_run") == "on"

    # JSON parsen
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            raise ValueError("Erwartet wird ein JSON-Array [ ... ]")
    except (json.JSONDecodeError, ValueError) as exc:
        return render(request, "fintech/watchlist_import.html", {
            "example_json": _WATCHLIST_IMPORT_EXAMPLE,
            "submitted_json": raw,
            "dry_run": dry_run,
            "error": f"Ungültiges JSON: {exc}",
        })

    total = len(entries)
    created = updated = 0
    errors = []
    details = []

    for idx, item in enumerate(entries, start=1):
        isin           = str(item.get("isin", "")).strip().upper()
        watchlist_name = str(item.get("watchlist", "")).strip()
        source         = str(item.get("source", "")).strip()
        notes          = str(item.get("notes", "")).strip()

        # Pflichtfelder prüfen
        if not isin:
            errors.append(f"Eintrag {idx}: 'isin' fehlt.")
            details.append({"isin": "–", "watchlist": watchlist_name, "status": "error", "price_at_add": None})
            continue
        if not watchlist_name:
            errors.append(f"Eintrag {idx} ({isin}): 'watchlist' fehlt.")
            details.append({"isin": isin, "watchlist": "–", "status": "error", "price_at_add": None})
            continue

        # Asset suchen
        try:
            asset = Asset.objects.get(isin=isin)
        except Asset.DoesNotExist:
            errors.append(f"Eintrag {idx}: Asset mit ISIN '{isin}' nicht gefunden.")
            details.append({"isin": isin, "watchlist": watchlist_name, "status": "error", "price_at_add": None})
            continue

        if not dry_run:
            # Watchlist anlegen falls nicht vorhanden
            watchlist, _ = Watchlist.objects.get_or_create(
                name=watchlist_name,
                user=request.user,
            )

            existing = WatchlistEntry.objects.filter(watchlist=watchlist, asset=asset).first()
            if existing:
                # Nur notes und source aktualisieren
                existing.notes  = notes
                existing.source = source
                existing.save(update_fields=["notes", "source"])
                updated += 1
                details.append({"isin": isin, "watchlist": watchlist_name, "status": "updated", "price_at_add": existing.price_at_add})
            else:
                entry = WatchlistEntry(watchlist=watchlist, asset=asset, source=source, notes=notes)
                entry.save()   # price_at_add wird in save() auto-befüllt
                created += 1
                details.append({"isin": isin, "watchlist": watchlist_name, "status": "created", "price_at_add": entry.price_at_add})
        else:
            # Dry-Run: nur prüfen ob Eintrag schon existiert
            wl_exists = Watchlist.objects.filter(name=watchlist_name, user=request.user).first()
            already_in = (
                WatchlistEntry.objects.filter(watchlist=wl_exists, asset=asset).exists()
                if wl_exists else False
            )
            status = "updated" if already_in else "created"
            if already_in:
                updated += 1
            else:
                created += 1
            details.append({"isin": isin, "watchlist": watchlist_name, "status": status, "price_at_add": asset.current_price})

    result = {
        "total":   total,
        "created": created,
        "updated": updated,
        "errors":  errors,
        "details": details,
        "dry_run": dry_run,
    }
    return render(request, "fintech/watchlist_import.html", {
        "example_json":   _WATCHLIST_IMPORT_EXAMPLE,
        "submitted_json": raw,
        "dry_run":        dry_run,
        "result":         result,
    })
