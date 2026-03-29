from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from .model_views import PortfolioSummary
import json
from decimal import Decimal

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