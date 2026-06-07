from django.contrib import admin
from django.db.models import Sum
from django.utils.html import format_html
from decimal import Decimal
from .models import Asset, Holdings, Price, WatchlistEntry, Watchlist, FiftyTwoWeekRange, NewsEvent
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

    def changelist_view(self, request, extra_context=None):
        # Bereinigung hier ausführen
        call_command('clean_up')
        return super().changelist_view(request, extra_context)
    
    list_display = (
        'get_asset_name',
        'quantity',
        'get_current_value',
        'average_purchase_price_display',
        'get_total_investment',
        'category',
        'not_for_sale',
        'stake_recovered',
    )
    list_filter = ('category', 'asset__asset_class', 'not_for_sale', 'stake_recovered')
    search_fields = ('asset__name', 'asset__symbol', 'asset__isin')
    autocomplete_fields = ('asset',)
    list_select_related = ('asset',)
    readonly_fields = ('get_total_investment', 'get_current_value', 'created_at', 'updated_at', 'get_week52_info')

    fieldsets = (
        (None, {'fields': ('asset', 'quantity', 'category', 'not_for_sale', 'stake_recovered')}),
        ('Finanzen', {'fields': ('average_purchase_price', 'get_total_investment', 'get_current_value')}),
        ('52-Wochen-Range', {'fields': ('get_week52_info',)}),
        ('Notizen', {'fields': ('notes',), 'classes': ('collapse',)}),
        ('Metadaten', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Asset', ordering='asset__name')
    def get_asset_name(self, obj):
        return f"{obj.asset.name} ({obj.asset.symbol or obj.asset.isin})"

    @admin.display(description='Gesamt Invest')
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

    @admin.display(description='52-Wochen-Range')
    def get_week52_info(self, obj):
        try:
            r = obj.asset.week52
        except Exception:
            return format_html('<span style="color:#aaa;">Noch nicht geladen — '
                               'wird beim nächsten Aufruf von /fintech/overall/ automatisch befüllt.</span>')

        if r.is_expired():
            return format_html('<span style="color:#dc3545;">Abgelaufen (älter als 52 Wochen) — '
                               'wird beim nächsten Seitenaufruf erneuert.</span>')

        cur = obj.asset.current_price
        def pct(cur, ref):
            if cur and ref:
                from decimal import Decimal
                return (Decimal(str(cur)) / Decimal(str(ref)) - 1) * 100
            return None

        pct_high = pct(cur, r.week52_high)
        pct_low  = pct(cur, r.week52_low)

        def fmt_pct(v):
            if v is None:
                return '–'
            sign = '+' if v >= 0 else ''
            color = '#198754' if v >= 0 else '#dc3545'
            return format_html('<span style="color:{};font-weight:600;">{}{:.1f} %</span>', color, sign, v)

        high_date = r.week52_high_date.strftime('%d.%m.%Y') if r.week52_high_date else '–'
        low_date  = r.week52_low_date.strftime('%d.%m.%Y')  if r.week52_low_date  else '–'
        fetched   = r.fetched_at.strftime('%d.%m.%Y %H:%M')

        return format_html(
            '<table style="border-collapse:collapse;font-size:.92rem;">'
            '<tr><td style="padding:.3rem 1.5rem .3rem 0;color:#6c757d;">52W-Hoch</td>'
            '    <td style="padding:.3rem 1rem .3rem 0;font-weight:600;">{} {}</td>'
            '    <td style="padding:.3rem 1rem .3rem 0;color:#6c757d;">({})</td>'
            '    <td>{}</td></tr>'
            '<tr><td style="padding:.3rem 1.5rem .3rem 0;color:#6c757d;">52W-Tief</td>'
            '    <td style="padding:.3rem 1rem .3rem 0;font-weight:600;">{} {}</td>'
            '    <td style="padding:.3rem 1rem .3rem 0;color:#6c757d;">({})</td>'
            '    <td>{}</td></tr>'
            '<tr><td colspan="4" style="padding-top:.5rem;font-size:.8rem;color:#aaa;">'
            '    Abgerufen: {}</td></tr>'
            '</table>',
            r.week52_high, obj.asset.currency, high_date, fmt_pct(pct_high),
            r.week52_low,  obj.asset.currency, low_date,  fmt_pct(pct_low),
            fetched,
        )

    @admin.display(description='Durchschnittspreis', ordering='average_purchase_price')
    def average_purchase_price_display(self, obj):
        if obj.average_purchase_price:
            price_str = f"{obj.average_purchase_price:.4f}"
            return format_html('{} {}', price_str, obj.asset.currency)
        return "–"

@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    list_display = ['asset', 'watchlist', 'formatted_price_at_add', 'current_profit_percent_formatted', 'source', 'added_at']
    list_filter = ['watchlist']
    search_fields = ('asset__name', 'asset__isin', 'asset__symbol', 'source', 'notes')
    autocomplete_fields = ('asset', 'watchlist')
    list_select_related = ('asset', 'watchlist')
    readonly_fields = ('added_at', 'formatted_price_at_add', 'current_profit_percent_formatted')

    fieldsets = (
        (None, {'fields': ('watchlist', 'asset')}),
        ('Kurs', {'fields': ('price_at_add', 'formatted_price_at_add', 'current_profit_percent_formatted')}),
        ('Dokumentation', {'fields': ('source', 'notes')}),
        ('Metadaten', {'fields': ('added_at',), 'classes': ('collapse',)}),
    )

    def formatted_price_at_add(self, obj):
        if obj.price_at_add:
            return f"{obj.price_at_add:.2f}"
        return "–"
    formatted_price_at_add.short_description = "Preis bei Aufnahme"

    def current_profit_percent_formatted(self, obj):
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


@admin.register(FiftyTwoWeekRange)
class FiftyTwoWeekRangeAdmin(admin.ModelAdmin):
    list_display  = ('asset', 'week52_high', 'week52_high_date', 'week52_low', 'week52_low_date', 'fetched_at')
    list_filter   = ('fetched_at',)
    search_fields = ('asset__isin', 'asset__symbol', 'asset__name')
    readonly_fields = ('fetched_at',)


@admin.register(NewsEvent)
class NewsEventAdmin(admin.ModelAdmin):
    list_display  = ('__str__', 'event_type', 'new_value', 'old_value', 'is_read', 'created_at')
    list_filter   = ('event_type', 'is_read', 'created_at')
    list_editable = ('is_read',)
    filter_horizontal = ('assets',)
    readonly_fields = ('created_at',)