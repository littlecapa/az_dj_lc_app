from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from decimal import Decimal
from .models import Asset, Holdings, Price, WatchlistEntry, Watchlist
from .model_views import PortfolioSummary
from django.template.response import TemplateResponse
from django.core.management import call_command

class PriceInline(admin.TabularInline):
    model = Price
    extra = 0
    ordering = ('-timestamp',)
    classes = ('collapse',)
    can_delete = True

@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ('asset', 'current_price_display', 'timestamp')
    list_filter = ('timestamp', 'asset__asset_class')
    search_fields = ('asset__name', 'asset__symbol', 'asset__isin')
    autocomplete_fields = ('asset',)
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)

    def current_price_display(self, obj):
        """Formatierter Preis mit Währung"""
        if obj.current_price:
            price_str = f"{obj.current_price:.4f}"
            return format_html('{} {}', price_str, 'EUR')
        return format_html('<span style="color: #999;">–</span>')

    current_price_display.short_description = 'Aktueller Preis'

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ['name', 'isin', 'current_price_display', 'current_price_timestamp', 'asset_class']
    list_filter = ['asset_class', 'currency', 'exchange']
    search_fields = ['isin', 'wkn', 'symbol', 'name']
    ordering = ('name',)
    inlines = [PriceInline]
    readonly_fields = ('created_at', 'updated_at', 'current_price', 'current_price_timestamp')
    
    fieldsets = (
        ('Basisdaten', {'fields': ('name', 'symbol', 'asset_class', 'currency')}),
        ('Marktdaten (Cache)', {
            'fields': ('current_price', 'current_price_timestamp'),
            'description': 'Aktualisiert automatisch via Price-Trigger.'
        }),
        ('Identifikation', {'fields': ('isin', 'wkn', 'exchange')}),
        ('Metadaten', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Aktueller Preis', ordering='current_price')
    def current_price_display(self, obj):
        """Formatierter Preis mit Währung"""
        if obj.current_price:
            price_str = f"{obj.current_price:.4f}"
            return format_html('{} {}', price_str, obj.currency or 'EUR')
        return format_html('<span style="color: #999;">–</span>')

    @admin.display(description='Preis-Update', ordering='current_price_timestamp')
    def current_price_timestamp(self, obj):
        """Formatierter Timestamp"""
        if obj.current_price_timestamp:
            return obj.current_price_timestamp.strftime('%d.%m.%Y %H:%M')
        return "Nie"

@admin.register(Holdings)
class HoldingsAdmin(admin.ModelAdmin):
    list_display = (
        'get_asset_name',
        'quantity',
        'get_current_value',
        'average_purchase_price_display',
        'get_total_investment',
        'category',
    )
    list_filter = ('category', 'asset__asset_class')
    search_fields = ('asset__name', 'asset__symbol', 'asset__isin')
    autocomplete_fields = ('asset',)
    list_select_related = ('asset',)
    readonly_fields = ('get_total_investment', 'created_at', 'updated_at')

    fieldsets = (
        (None, {'fields': ('asset', 'quantity', 'category')}),
        ('Finanzen', {'fields': ('average_purchase_price', 'get_total_investment')}),
        ('Notizen', {'fields': ('notes',), 'classes': ('collapse',)}),
        ('Metadaten', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Asset', ordering='asset__name')
    def get_asset_name(self, obj):
        return f"{obj.asset.name} ({obj.asset.symbol or obj.asset.isin})"

    @admin.display(description='Gesamtwert (Invest)')
    def get_total_investment(self, obj):
        if obj.total_investment:
            value_str = f"{obj.total_investment:.2f}"
            return format_html('{} {}', value_str, obj.asset.currency)
        return "–"

    @admin.display(description='Marktwert (Aktuell)')
    def get_current_value(self, obj):
        if obj.asset.current_price:
            value = obj.quantity * obj.asset.current_price
            value_str = f"{value:.2f}"
            return format_html('{} {}', value_str, obj.asset.currency)
        return "–"

    @admin.display(description='Durchschnittspreis', ordering='average_purchase_price')
    def average_purchase_price_display(self, obj):
        if obj.average_purchase_price:
            price_str = f"{obj.average_purchase_price:.4f}"
            return format_html('{} {}', price_str, obj.asset.currency)
        return "–"

@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    list_display = ['asset', 'watchlist', 'formatted_price_at_add', 'current_profit_percent_formatted']
    list_filter = ['watchlist']
    autocomplete_fields = ('asset', 'watchlist')
    list_select_related = ('asset', 'watchlist')

    def formatted_price_at_add(self, obj):
        """Preis bei Aufnahme formatiert"""
        if obj.price_at_add:
            return f"{obj.price_at_add:.2f}"
        return "-"
    formatted_price_at_add.short_description = "Preis bei Aufnahme"

    def current_profit_percent_formatted(self, obj):
        """Performance seit Aufnahme formatiert"""
        profit = obj.current_profit_percent
        if profit is not None:
            return f"{profit:+.1f}%"
        return "–"
    current_profit_percent_formatted.short_description = "Performance"

@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):  # WatchEntryAdmin → WatchlistAdmin (Fix)
    list_display = ['name', 'user', 'asset_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'user__username']
    
    def asset_count(self, obj):
        """Anzahl Assets in Watchlist"""
        return obj.entries.count()
    asset_count.short_description = "Assets"

@admin.register(PortfolioSummary)
class PortfolioSummaryAdmin(admin.ModelAdmin):
    readonly_fields = [
        'name',
        'isin',
        'asset_class',        # war category_display — existiert nicht im Model
        'total_quantity',
        'purchase_price',
        'current_value',
        'delta_abs',
        'delta_perc',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        call_command('update_prices')  # Preise vor Anzeige aktualisieren
        context = dict(extra_context or {})
        context['portfolio'] = list(PortfolioSummary.objects.portfolio())
        return TemplateResponse(
            request,
            'admin/fintech/portfolio_summary_changelist.html',
            context,
        )