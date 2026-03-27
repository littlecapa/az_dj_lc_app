from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from .models import Asset, Holdings, Price  # Bleibt Holdings (dein Modellname)

class PriceInline(admin.TabularInline):
    model = Price
    extra = 0
    ordering = ('-timestamp',)
    classes = ('collapse',)
    can_delete = True

@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ('asset', 'current_price', 'timestamp')
    list_filter = ('timestamp', 'asset__asset_class')  # asset_class -> assetclass korrigiert?
    search_fields = ('asset__name', 'asset__symbol', 'asset__isin')
    autocomplete_fields = ('asset',)
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ['name', 'isin', 'current_price_display', 'current_price_timestamp', 'asset_class']  # Quotes fix + extra Feld
    list_filter = ['asset_class', 'currency', 'exchange']  # asset_class konsistent
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
            return format_html('{:.4f} {}', obj.current_price, obj.currency or 'EUR')
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
        'average_purchase_price',
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
        if obj.total_investment:  # Property aus Model
            return format_html('{:.2f} {}', obj.total_investment, obj.asset.currency)
        return "–"

    @admin.display(description='Marktwert (Aktuell)')
    def get_current_value(self, obj):
        if obj.asset.current_price:
            value = obj.quantity * obj.asset.current_price
            return format_html('{:.2f} {}', value, obj.asset.currency)
        return "–"
