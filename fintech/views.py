from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from .model_views import PortfolioSummary
import json
from decimal import Decimal
from .apis.services.csv_import import import_transactions
from django.contrib import messages
from django.core.management import call_command
from django.views.decorators.cache import never_cache

import logging

logger = logging.getLogger(__name__)

def decimal_serializer(obj):
    """JSON-Serializer für Decimal-Felder."""
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
 
@staff_member_required
def portfolio_export(request):
    data = list(PortfolioSummary.objects.portfolio())
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
