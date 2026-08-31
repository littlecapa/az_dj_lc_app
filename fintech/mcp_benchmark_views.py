"""
Benchmark: vergleicht Kurs + Antwortzeit der bisherigen Kursquelle (ProviderManager,
i.d.R. Comdirect+Yahoo) mit der neuen Scalable-MCP-Anbindung
(fintech.apis.services.mcp_scalable.ScalableMcpRequest) für alle Assets mit Bestand.

Rein diagnostisch — berührt update_prices/ProviderManager nicht (siehe deren eigene,
unveränderte Dateien). Lebt bewusst in fintech (nicht core), da es fintech-Modelle und
-Provider braucht; die URL liegt trotzdem unter core:mcp_scalable_* (core/urls.py
referenziert diese Views direkt), damit sie sich in /mcp/scalable/... einreiht.
"""
import asyncio
import logging
import time
from decimal import InvalidOperation

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.mcp_client import has_valid_token
from core.models import McpConnection

from .apis.services.exchange_rate_proxy import CurrencyProxy
from .apis.services.mcp_scalable import ScalableMcpNotConnectedError, ScalableMcpRequest
from .apis.services.provider_manager import ProviderManager
from .apis.services.request_lib import KeyNotFoundError, KeyNotFoundWarning
from .libs.general.converter import string2dec
from .models import Asset

logger = logging.getLogger(__name__)

BENCHMARK_CONCURRENCY = 5


def _is_connected(request) -> bool:
    """Gleiche Definition wie core.views.mcp_scalable_page: gültiger Token + diese Session hat ihn verifiziert."""
    connection, _ = McpConnection.objects.get_or_create(
        user=request.user, provider=McpConnection.Provider.SCALABLE,
        defaults={"mcp_server_url": "https://mcp.scalable.capital/mcp"},
    )
    return has_valid_token(connection) and request.session.get("mcp_scalable_connected", False)


@never_cache
@login_required
def mcp_scalable_benchmark_page(request):
    """GET: zeigt Start-Button (nur aktiv wenn verbunden) + ggf. Ergebnisse aus vorherigem Lauf."""
    return render(request, "core/mcp_scalable_benchmark.html", {"connected": _is_connected(request)})


@login_required
@require_POST
def mcp_scalable_benchmark_run(request):
    """POST: führt den Benchmark aus und rendert die Ergebnistabelle direkt (kein Redirect —
    die Ergebnisliste kann für große Portfolios zu groß für die Session sein)."""
    if not _is_connected(request):
        return render(request, "core/mcp_scalable_benchmark.html", {
            "connected": False,
            "error": "Nicht verbunden — Benchmark abgebrochen.",
        })

    assets = list(Asset.objects.filter(holdings__isnull=False).distinct().order_by("name"))
    rows = async_to_sync(_run_benchmark)(assets)

    total_delta_time_ms = sum(r["delta_time_ms"] for r in rows if r["delta_time_ms"] is not None)

    return render(request, "core/mcp_scalable_benchmark.html", {
        "connected": True,
        "rows": rows,
        "total_delta_time_ms": total_delta_time_ms,
        "total_delta_time_s": round(total_delta_time_ms / 1000, 2),
        "asset_count": len(assets),
    })


# ----------------------------------------------------------------------
# Async-Ausführung (Muster wie fintech.management.commands.update_prices):
# Semaphore begrenzt die Parallelität, jeder synchrone Provider-Call läuft über
# asyncio.to_thread. Pro Asset laufen alte API + MCP-API zusätzlich parallel
# zueinander (asyncio.gather), damit die Gesamtlaufzeit nicht Summe, sondern
# Maximum beider Aufrufe ist.

async def _run_benchmark(assets: list[Asset]) -> list[dict]:
    semaphore = asyncio.Semaphore(BENCHMARK_CONCURRENCY)
    tasks = [_benchmark_asset(asset, semaphore) for asset in assets]
    return await asyncio.gather(*tasks)


async def _benchmark_asset(asset: Asset, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        old_task = asyncio.to_thread(_timed_old_price, asset)
        mcp_task = asyncio.to_thread(_timed_mcp_price, asset.isin)
        (old_price, old_time_ms, old_error), (mcp_price, mcp_time_ms, mcp_error) = await asyncio.gather(
            old_task, mcp_task
        )

    row = {
        "isin": asset.isin,
        "name": asset.name,
        "old_price": old_price,
        "old_time_ms": old_time_ms,
        "old_error": old_error,
        "mcp_price": mcp_price,
        "mcp_time_ms": mcp_time_ms,
        "mcp_error": mcp_error,
        "delta_time_ms": None,
        "delta_price_abs": None,
        "delta_price_pct": None,
    }

    if old_time_ms is not None and mcp_time_ms is not None:
        row["delta_time_ms"] = mcp_time_ms - old_time_ms

    if old_price is not None and mcp_price is not None:
        delta_abs = abs(mcp_price - old_price)
        row["delta_price_abs"] = delta_abs
        if old_price != 0:
            row["delta_price_pct"] = (delta_abs / old_price) * 100

    return row


def _timed_old_price(asset: Asset):
    """Bisherige API (ProviderManager, i.d.R. Comdirect+Yahoo). Return (price|None, ms, error|None)."""
    start = time.monotonic()
    try:
        price = ProviderManager().isin2price(asset.isin, asset.asset_class, yahoo_symbol=asset.yahoo_symbol)
    except Exception as exc:
        return None, round((time.monotonic() - start) * 1000), str(exc)

    elapsed_ms = round((time.monotonic() - start) * 1000)
    if price is None:
        return None, elapsed_ms, "Kein Preis verfügbar"
    return price, elapsed_ms, None


def _timed_mcp_price(isin: str):
    """Scalable-MCP-API. Return (price_in_eur|None, ms, error|None)."""
    start = time.monotonic()
    try:
        price_str, currency = ScalableMcpRequest().isin2price(isin)
    except ScalableMcpNotConnectedError as exc:
        return None, round((time.monotonic() - start) * 1000), str(exc)
    except (KeyNotFoundWarning, KeyNotFoundError) as exc:
        return None, round((time.monotonic() - start) * 1000), str(exc)

    elapsed_ms = round((time.monotonic() - start) * 1000)
    try:
        price = string2dec(price_str)
        if currency != "EUR":
            rate = CurrencyProxy().get_rate(currency)
            price = price / rate
    except InvalidOperation:
        return None, elapsed_ms, f"Ungültiger Kurswert: {price_str}"
    except Exception as exc:
        return None, elapsed_ms, f"Währungsumrechnung fehlgeschlagen: {exc}"

    return price, elapsed_ms, None
