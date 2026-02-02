from django.db import models
from decimal import Decimal

from django.core.validators import MinValueValidator

# Create your models here.

class Asset(models.Model):
    """
    Grundsätzliche Informationen zu einem Asset (Aktie, ETF, etc.)
    """
    
    class AssetClass(models.TextChoices):
        STOCK = 'STOCK', 'Aktie'
        ETF = 'ETF', 'ETF'
        ETC = 'ETC', 'ETC'
        CRYPTO = 'CRYPTO', 'Kryptowährung'
        DERIVATIVE = 'DERIVATIVE', 'Derivat'
    
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
        max_length=10,
        help_text="Börsenkürzel (z.B. AAPL, SAP)",
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
    
    currency = models.CharField(
        max_length=3,
        default='EUR',
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
    
    class Category(models.IntegerChoices):
        BASIS_INVESTMENT = 1, 'Basis Investment'
        DIVIDENDE = 2, 'Dividende'
        D_EU = 3, 'D/EU'
        US_TECH = 4, 'US Tech'
        WORLD_TECH = 5, 'World Tech'
        COMPOUNDER = 6, 'Compounder'
        SONSTIGES = 99, 'Sonstiges'
    
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
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Durchschnittlicher Einkaufspreis"
    )
    
    category = models.IntegerField(
        choices=Category.choices,
        default=Category.SONSTIGES,
        null=True,
        blank=True,
        help_text="Kategorie der Investment-Strategie"
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

