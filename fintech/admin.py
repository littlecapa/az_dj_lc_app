from django.contrib import admin
from django.db.models import Sum
from .models import Asset, Holdings, Price

class PriceInline(admin.TabularInline):
    """
    Erlaubt das Bearbeiten von Kursen direkt im Asset
    """
    model = Price
    extra = 0
    ordering = ('-timestamp',)
    classes = ('collapse',) # Standardmäßig zugeklappt bei vielen Einträgen
    can_delete = True
    
    # Optional: Felder readonly machen, wenn man die Historie schützen will
    # readonly_fields = ('timestamp', 'amount')

@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ('asset', 'amount', 'timestamp')
    list_filter = (
        'timestamp',         # Fügt Filter für Heute, Letzte 7 Tage etc. hinzu
        'asset__asset_class'
    )
    search_fields = ('asset__name', 'asset__symbol', 'asset__isin')
    autocomplete_fields = ('asset',) # Wichtig für Performance
    date_hierarchy = 'timestamp'     # Navigationsleiste nach Datum oben
    ordering = ('-timestamp',)

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        'name', 
        'symbol', 
        'asset_class', 
        'current_price',        # Neu
        'current_price_timestamp', # Neu
        'currency'
    )
    list_filter = ('asset_class', 'exchange', 'currency')
    search_fields = ('name', 'symbol', 'isin', 'wkn')
    ordering = ('name',)
    
    # Inline hinzufügen
    inlines = [PriceInline]
    
    # Neue Felder als Read-Only definieren (werden via Price-Update gesetzt)
    readonly_fields = ('created_at', 'updated_at', 'current_price', 'current_price_timestamp')
    
    fieldsets = (
        ('Basisdaten', {
            'fields': ('name', 'symbol', 'asset_class', 'currency')
        }),
        ('Marktdaten (Cache)', { # Neuer Abschnitt
            'fields': ('current_price', 'current_price_timestamp'),
            'description': 'Diese Werte aktualisieren sich automatisch, wenn ein neuer Kurs eingetragen wird.'
        }),
        ('Identifikation', {
            'fields': ('isin', 'wkn', 'exchange')
        }),
        ('Metadaten', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

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
    list_filter = (
        'category', 
        'asset__asset_class',  # Filtert nach Eigenschaften des verknüpften Assets
    )
    search_fields = ('asset__name', 'asset__symbol', 'asset__isin')
    autocomplete_fields = ('asset',)  # Nutzt die Suche aus AssetAdmin
    list_select_related = ('asset',)  # Performance-Optimierung (JOIN statt n+1 Queries)
    readonly_fields = ('get_total_investment', 'created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('asset', 'quantity', 'category')
        }),
        ('Finanzen', {
            'fields': ('average_purchase_price', 'get_total_investment'),
        }),
        ('Notizen', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Metadaten', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Asset', ordering='asset__name')
    def get_asset_name(self, obj):
        return obj.asset.name

    @admin.display(description='Gesamtwert (Invest)', ordering='quantity')
    def get_total_investment(self, obj):
        if obj.total_investment:
            return f"{obj.total_investment:,.2f} {obj.asset.currency}"
        return "-"
    
    @admin.display(description='Marktwert (Aktuell)', ordering='asset__current_price')
    def get_current_value(self, obj):
        # Zeigt: Menge * Aktueller Börsenkurs
        if obj.asset.current_price:
            value = obj.quantity * obj.asset.current_price
            return f"{value:,.2f} {obj.asset.currency}"
        return "-"
