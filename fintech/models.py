from django.db import models
from decimal import Decimal
import re
from django.core.validators import MinValueValidator
from .models_helper.asset_class import AssetClass
from .models_helper.currency_class import CurrencyClass
from .models_helper.category_class import CategoryClass

from django.utils import timezone
from django.contrib.auth.models import User
    
class Asset(models.Model):
    """
    Grundsätzliche Informationen zu einem Asset (Aktie, ETF, etc.)
    """
    
    # ISIN als PK - international eindeutig
    isin = models.CharField(
        max_length=12, 
        primary_key=True,
        verbose_name="ISIN",
        help_text="Internationale Wertpapierkennnummer (12 Zeichen)",
    )
    
    wkn = models.CharField(
        max_length=6, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="Wertpapierkennnummer (6 Zeichen, hauptsächlich für deutsche Werte)",
    )
    
    symbol = models.CharField(
        max_length=20,
        help_text="TradingView-Symbol (z.B. XETR:RHM, NASDAQ:AAPL)",
        null=True, 
        blank=True
    )
    
    name = models.CharField(
        max_length=200,
        help_text="Vollständiger Name des Assets/Unternehmens"
    )
    
    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.STOCK,
        help_text="Art des Assets"
    )

    asset_class = models.CharField(
        max_length=10,
        choices=AssetClass.choices,
        default=AssetClass.STOCK,
        help_text="Art des Assets"
    )
    
    currency = models.CharField(
        max_length=3,
        default='EUR',
        choices=CurrencyClass.choices,
        help_text="Währung als ISO-Code (EUR, USD, etc.)"
    )
    
    exchange = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Hauptbörse (XETRA, NYSE, NASDAQ, etc.)",
    )

    # Neue Felder für Performance-Optimierung
    current_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True, 
        blank=True,
        help_text="Letzter bekannter Kurs (Cache)"
    )
    current_price_timestamp = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Zeitpunkt des letzten Kurses"
    )

    logo = models.URLField(
        blank=True,
        null=True,
        help_text="Logo-URL, z.B. https://s3-symbol-logo.tradingview.com/iberdrola--big.svg"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Asset"
        verbose_name_plural = "Assets"
        ordering = ['name']
        indexes = [
            models.Index(fields=['asset_class']),
            models.Index(fields=['symbol']),
        ]

    def __str__(self):
        return f"{self.name} ({self.symbol or self.isin})"


class Holdings(models.Model):
    """
    Bestand an Assets pro Benutzer
    """
    
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='holdings'
    )
    
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text="Anzahl gehaltener Anteile (auch Bruchteile möglich)"
    )
    
    average_purchase_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Durchschnittlicher Einkaufspreis"
    )
    
    category = models.IntegerField(
        choices=CategoryClass.choices,
        default=CategoryClass.MISCELLANEOUS,
        null=True,
        blank=True,
        help_text="Kategorie der Investment-Strategie"
    )
    
    not_for_sale = models.BooleanField(
        default=False,
        help_text=(
            "Position aktuell nicht zum Verkauf vorgesehen "
            "(z. B. VL-Sperre, Unternehmensaktien, emotionale Gründe)"
        ),
    )

    stake_recovered = models.BooleanField(
        default=False,
        help_text=(
            "Original stake already recovered through profit-taking — "
            "remaining position is essentially 'free'."
        ),
    )

    notes = models.TextField(
        help_text="Persönliche Notizen zu dieser Position",
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bestand"
        verbose_name_plural = "Bestände"
        unique_together = ['asset']
        ordering = ['-quantity']

    def __str__(self):
        return f"{self.asset.name}: {self.quantity} ({self.asset.symbol or self.asset.isin})"

    @property
    def total_investment(self):
        """Berechnet den Einstandswert (Kosten)"""
        if self.average_purchase_price:
            return self.quantity * self.average_purchase_price
        return None

    @property
    def current_market_value(self):
        """Berechnet den aktuellen Marktwert basierend auf dem letzten Kurs"""
        if self.asset.current_price:
            return self.quantity * self.asset.current_price
        return None

    @property
    def profit_loss(self):
        """Berechnet den absoluten Gewinn/Verlust"""
        market_value = self.current_market_value
        invested = self.total_investment
        
        if market_value is not None and invested is not None:
            return market_value - invested
        return None

    
class Price(models.Model):
    """
    Historische Kurse zu einem Asset
    """
    asset = models.ForeignKey(
        'Asset', # String-Referenz vermeidet Zirkelbezüge
        on_delete=models.CASCADE,
        related_name='prices'
    )
    timestamp = models.DateTimeField(
        help_text="Zeitpunkt der Kursfeststellung"
    )
    current_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text="Kurs in Währung des Assets zum Zeitpunkt ..."
    )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Prüfen, ob dies der neueste Kurs ist
        latest_price = self.asset.prices.first() # Dank ordering='-timestamp' ist das der neueste
        if latest_price and (
            self.asset.current_price_timestamp is None or
            latest_price.timestamp >= self.asset.current_price_timestamp
        ):
            self.asset.current_price = latest_price.current_price
            self.asset.current_price_timestamp = latest_price.timestamp
            self.asset.save(update_fields=['current_price', 'current_price_timestamp'])
        # 52W-Hoch/Tief aktualisieren falls vorhanden
        self._update_week52(self.current_price)

    def _update_week52(self, price):
        """Prüft ob der neue Kurs ein neues 52W-Hoch oder -Tief darstellt."""
        try:
            r = self.asset.week52
        except Exception:
            return  # Noch kein Range-Eintrag → nichts zu tun

        if r.is_expired():
            r.delete()
            return

        today = timezone.now().date()
        changed = False

        if price > r.week52_high:
            event = NewsEvent.objects.create(
                event_type=NewsEvent.EventType.NEW_HIGH,
                old_value=r.week52_high,
                new_value=price,
            )
            event.assets.add(self.asset)
            r.week52_high = price
            r.week52_high_date = today
            changed = True

        if price < r.week52_low:
            event = NewsEvent.objects.create(
                event_type=NewsEvent.EventType.NEW_LOW,
                old_value=r.week52_low,
                new_value=price,
            )
            event.assets.add(self.asset)
            r.week52_low = price
            r.week52_low_date = today
            changed = True

        if changed:
            r.save(update_fields=['week52_high', 'week52_high_date', 'week52_low', 'week52_low_date'])

    class Meta:
        verbose_name = "Kurs"
        verbose_name_plural = "Kurse"
        ordering = ['-timestamp'] # Neueste zuerst
        indexes = [
            models.Index(fields=['asset', '-timestamp']), # Performanter Zugriff auf Historie
        ]
        # Optional: Nur ein Kurs pro Zeitpunkt pro Asset
        unique_together = ['asset', 'timestamp'] 

    
    def __str__(self):
        return f"{self.asset.symbol}: {self.current_price} ({self.timestamp:%Y-%m-%d %H:%M})"

class Watchlist(models.Model):
    """
    Benutzer-Watchlist für Assets
    """
    name = models.CharField(
        max_length=100,
        help_text="Name der Watchlist (z.B. 'US Tech Favoriten')"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='watchlists',
        help_text="Besitzer der Watchlist"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Watchlist"
        verbose_name_plural = "Watchlists"
        unique_together = ['name', 'user']  # User kann keine Dupe-Namen haben
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    @property
    def asset_count(self):
        return self.entries.count()


class WatchlistEntry(models.Model):
    """
    Asset-Eintrag in Watchlist mit Add-Datum + damaligem Kurs
    """
    watchlist = models.ForeignKey(
        Watchlist,
        on_delete=models.CASCADE,
        related_name='entries'
    )
    asset = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        help_text="Beobachtetes Asset"
    )
    added_at = models.DateTimeField(
        default=timezone.now,
        help_text="Zeitpunkt der Aufnahme in Watchlist"
    )
    price_at_add = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text="Kurs zum Zeitpunkt der Aufnahme (wird automatisch befüllt)",
    )
    source = models.CharField(
        max_length=300,
        blank=True,
        help_text="Quelle des Eintrags (z. B. URL, Analyst, Nachricht)",
    )
    notes = models.CharField(
        max_length=500,
        blank=True,
        help_text="Grund für Watchlist-Aufnahme",
    )

    class Meta:
        verbose_name = "Watchlist-Eintrag"
        verbose_name_plural = "Watchlist-Einträge"
        unique_together = ['watchlist', 'asset']
        indexes = [
            models.Index(fields=['watchlist', 'added_at']),
            models.Index(fields=['asset']),
        ]
        ordering = ['-added_at']  # Neueste zuerst

    def save(self, *args, **kwargs):
        # Beim ersten Speichern: aktuellen Kurs als Einstiegskurs übernehmen
        if self.pk is None and self.price_at_add is None:
            if self.asset_id and hasattr(self, 'asset') and self.asset.current_price:
                self.price_at_add = self.asset.current_price
        super().save(*args, **kwargs)

    def __str__(self):
        price_str = f"{self.price_at_add}" if self.price_at_add else "kein Kurs"
        return f"{self.asset.symbol or self.asset.isin} → {self.watchlist.name} ({price_str})"

    @property
    def current_profit_percent(self):
        """Performance seit Aufnahme (%)"""
        if self.asset.current_price and self.price_at_add:
            return ((self.asset.current_price / self.price_at_add) - 1) * 100
        return None


class FiftyTwoWeekRange(models.Model):
    """
    52-Wochen-Hoch und -Tief für ein Asset.
    Wird lazy über die Yahoo-Finance-API befüllt und in der DB gecacht.
    Ablauf: fetched_at älter als 52 Wochen → Datensatz löschen und neu holen.
    """
    asset = models.OneToOneField(
        Asset,
        on_delete=models.CASCADE,
        related_name='week52',
    )
    week52_high = models.DecimalField(
        max_digits=12, decimal_places=4,
        help_text="52-Wochen-Hoch in Asset-Währung",
    )
    week52_high_date = models.DateField(
        null=True, blank=True,
        help_text="Datum, an dem das 52-Wochen-Hoch zuletzt aktualisiert wurde",
    )
    week52_low = models.DecimalField(
        max_digits=12, decimal_places=4,
        help_text="52-Wochen-Tief in Asset-Währung",
    )
    week52_low_date = models.DateField(
        null=True, blank=True,
        help_text="Datum, an dem das 52-Wochen-Tief zuletzt aktualisiert wurde",
    )
    fetched_at = models.DateTimeField(
        default=timezone.now,
        help_text="Zeitpunkt des letzten API-Abrufs",
    )

    class Meta:
        verbose_name = "52-Wochen-Range"
        verbose_name_plural = "52-Wochen-Ranges"

    def __str__(self):
        return f"{self.asset.symbol or self.asset.isin}: H={self.week52_high} T={self.week52_low}"

    def is_expired(self) -> bool:
        """True wenn die Daten älter als 52 Wochen sind."""
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(weeks=52)
        return self.fetched_at < cutoff


class NewsEvent(models.Model):
    """
    Markt-Ereignis (z. B. neues 52W-Hoch/-Tief, später auch RSS-Feeds).
    Kann mehreren Assets zugeordnet sein.
    """
    class EventType(models.TextChoices):
        NEW_HIGH = 'new_high', 'Neues 52W-Hoch'
        NEW_LOW  = 'new_low',  'Neues 52W-Tief'

    assets = models.ManyToManyField(
        Asset,
        related_name='news_events',
        blank=True,
    )
    event_type = models.CharField(
        max_length=20, choices=EventType.choices,
    )
    old_value = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        help_text="Bisheriger Extremwert",
    )
    new_value = models.DecimalField(
        max_digits=12, decimal_places=4,
        help_text="Neuer Extremwert",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "News-Event"
        verbose_name_plural = "News-Events"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_event_type_display()} @ {self.new_value} ({self.created_at:%Y-%m-%d})"
