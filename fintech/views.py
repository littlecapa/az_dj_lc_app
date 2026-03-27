import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.generic import TemplateView
from django.conf import settings
import logging
from collections import defaultdict
import time
from django.utils import timezone
from decimal import Decimal
from .models import Holdings, Asset, Price
from django.core.cache import cache  # Füge Import hinzu

logger = logging.getLogger(__name__)

class AssetPriceView(APIView):
    """Bestehende API-View (bleibt unverändert)"""
    def get(self, request):
        isin = request.query_params.get('isin')
        currency = request.query_params.get('currency', 'EUR')
        
        if not isin:
            return Response({'error': 'ISIN erforderlich'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Schritt 1: ISIN zu Symbol mappen
        search_url = f"https://financialmodelingprep.com/api/v3/search/isin"
        params = {'isin': isin, 'apikey': settings.FMP_API_KEY}
        try:
            search_resp = requests.get(search_url, params=params)
            search_data = search_resp.json()
            if not search_data:
                return Response({'error': 'ISIN nicht gefunden'}, status=status.HTTP_404_NOT_FOUND)
            symbol = search_data[0]['symbol']
            logger.info(f"ISIN {isin} -> Symbol {symbol}")
        except Exception as e:
            logger.error(f"ISIN-Suche fehlgeschlagen: {e}")
            return Response({'error': 'API-Fehler bei ISIN-Suche'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Schritt 2: Kurs holen
        quote_url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
        params = {'apikey': settings.FMP_API_KEY}
        try:
            quote_resp = requests.get(quote_url, params=params)
            quote_data = quote_resp.json()
            if not quote_data:
                return Response({'error': 'Kurs nicht verfügbar'}, status=status.HTTP_404_NOT_FOUND)
            
            price_info = quote_data[0]
            result = {
                'isin': isin,
                'symbol': symbol,
                'price': price_info['price'],
                'currency': currency,
                'last_update': price_info['timestamp']
            }
            return Response(result)
        except Exception as e:
            logger.error(f"Kurs-Abfrage fehlgeschlagen: {e}")
            return Response({'error': 'API-Fehler bei Kurs'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class OverviewView(TemplateView):
    """HTML-View mit automatischer Preis-Update + Tabelle"""
    template_name = 'fintech/overview.html'

    def _fetch_and_update_price(self, asset):
        """Wiederverwendbare FMP-Logik -> erstellt Price (Trigger updated current_price)"""
        cache_key = f"price_{asset.isin}"
        cached_price = cache.get(cache_key)
        if cached_price and (timezone.now() - cache.get(f"price_time_{asset.isin}", timezone.now())).seconds < 300:  # 5 Min Cache
            return cached_price
        
        if not asset.isin:
            return None
        
        try:
            # Identisch mit AssetPriceView
            search_url = f"https://financialmodelingprep.com/api/v3/search/isin"
            params = {'isin': asset.isin, 'apikey': settings.FMP_API_KEY}
            search_resp = requests.get(search_url, params=params)
            search_data = search_resp.json()
            if not search_data:
                return None
            symbol = search_data[0]['symbol']
            logger.info(f"Updating price for {asset.isin} -> Symbol {symbol}")
            
            quote_url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
            params = {'apikey': settings.FMP_API_KEY}
            quote_resp = requests.get(quote_url, params=params)
            quote_data = quote_resp.json()
            if quote_data:
                price = Decimal(str(quote_data[0]['price']))
                Price.objects.create(
                    asset=asset,
                    current_price=price,
                    timestamp=timezone.now()
                )
                logger.info(f"Updated price for {asset.isin}: {price}")
                return price
        except Exception as e:
            logger.error(f"Price update failed for {asset.isin}: {e} symbol: {symbol if 'symbol' in locals() else ''    }")
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 1. Preise für alle Holdings-Assets updaten
        holdings_assets = Asset.objects.filter(holdings__isnull=False).distinct()
        for asset in holdings_assets:
            self._fetch_and_update_price(asset)

        # 2. Holdings laden (sortiert nach Category)
        holdings = Holdings.objects.select_related('asset').order_by('category')
        table_data = []
        category_totals = defaultdict(lambda: {'purchase': Decimal('0'), 'current': Decimal('0')})
        grand_totals = {'purchase': Decimal('0'), 'current': Decimal('0')}

        for holding in holdings:
            purchase = holding.total_investment or Decimal('0')
            current = holding.current_market_value or Decimal('0')
            profit_loss = current - purchase
            profit_pct = (profit_loss / purchase * 100) if purchase > 0 else Decimal('0')
            
            row = {
                'name': f"{holding.asset.name} ({holding.asset.symbol or holding.asset.isin})",
                'category': holding.get_category_display() or 'Sonstiges',
                'quantity': float(holding.quantity),
                'total_purchase_price': float(purchase),
                'total_current_value': float(current),
                'profit_loss': float(profit_loss),
                'profit_pct': float(profit_pct),
                'is_subtotal': False,
                'is_grand_total': False
            }
            table_data.append(row)
            
            cat_id = holding.category or 99
            category_totals[cat_id]['purchase'] += purchase
            category_totals[cat_id]['current'] += current
            grand_totals['purchase'] += purchase
            grand_totals['current'] += current

        # 3. Zwischensummen + Grand Total bauen
        final_data = []
        for cat_id in sorted(category_totals):
            cat_name = Holdings.Category(cat_id).label if hasattr(Holdings.Category, str(cat_id)) else 'Sonstiges'
            # Holdings dieser Kategorie hinzufügen
            cat_holdings = [r for r in table_data if r['category'] == cat_name]
            final_data.extend(cat_holdings)
            
            # Zwischensumme
            totals = category_totals[cat_id]
            pl = totals['current'] - totals['purchase']
            pl_pct = (pl / totals['purchase'] * 100) if totals['purchase'] > 0 else Decimal('0')
            final_data.append({
                'name': f'Zwischensumme {cat_name}',
                'category': '',
                'quantity': None,
                'total_purchase_price': float(totals['purchase']),
                'total_current_value': float(totals['current']),
                'profit_loss': float(pl),
                'profit_pct': float(pl_pct),
                'is_subtotal': True,
                'is_grand_total': False
            })

        # Grand Total
        gt_pl = grand_totals['current'] - grand_totals['purchase']
        gt_pct = (gt_pl / grand_totals['purchase'] * 100) if grand_totals['purchase'] > 0 else Decimal('0')
        final_data.append({
            'name': 'Gesamt Portfolio',
            'category': '',
            'quantity': None,
            'total_purchase_price': float(grand_totals['purchase']),
            'total_current_value': float(grand_totals['current']),
            'profit_loss': float(gt_pl),
            'profit_pct': float(gt_pct),
            'is_subtotal': False,
            'is_grand_total': True
        })

        context.update({
            'holdings': final_data,
            'timestamp': timezone.now().strftime('%d.%m.%Y %H:%M'),
            'total_portfolio_value': sum(r['total_current_value'] for r in final_data if not r.get('is_subtotal') and not r.get('is_grand_total'))
        })
        return context
