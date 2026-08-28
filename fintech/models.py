from django.db import models
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from .models_helper.asset_class import AssetClass
from .models_helper.currency_class import CurrencyClass
from .models_helper.category_class import CategoryClass
from .models_helper.etf_extend_source import EtfExtendSource

from django.utils import timezone
from django.contrib.auth.models import User
from telegram_app.libs.telegram_api import send_telegram_message


class FinConfig(models.Model):
    """
    Singleton-Tabelle für App-weite Konfigurationswerte.
    Immer nur ein Datensatz (pk=1). Zugriff über FinConfig.get().
    """
    week52_no_date_ttl_days = models.PositiveIntegerField(
        default=7,
        verbose_name="52W-Range TTL ohne Datum (Tage)",
        help_text=(
            "Wie viele Tage ein 52W-Range-Eintrag ohne Datum (Yahoo liefert keins) "
            "als gültig gilt, bevor er neu abgerufen wird."
        ),
    )

    class Meta:
        verbose_name = "Fintech-Konfiguration"
        verbose_name_plural = "Fintech-Konfiguration"

    def __str__(self):
        return "Fintech-Konfiguration"

    @classmethod
    def get(cls) -> "FinConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
    
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

    yahoo_symbol = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text=(
            "Manueller Yahoo-Finance-Ticker (z.B. 'AAL.L'), falls Yahoos ISIN-Suche "
            "für dieses Asset nichts findet (isin2price schlägt sonst fehl). Nur "
            "setzen, wenn nötig — sonst wird die ISIN-Suche normal verwendet. "
            "Achtung: anderes Format als 'symbol' (TradingView)."
        ),
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

    price_fetch_blocked = models.BooleanField(
        default=False,
        help_text=(
            "True = kein automatischer Kurs-Abruf mehr (es existiert bereits ein "
            "offenes Jira-Bug-Ticket dazu, da der Abruf seit über 24h fehlschlägt). "
            "Nach Bearbeitung des Tickets manuell wieder auf False setzen."
        ),
    )
    price_fetch_failing_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Zeitpunkt des ersten fehlgeschlagenen Kurs-Abrufs in Folge. Wird bei "
            "jedem erfolgreichen Abruf zurückgesetzt. Erst wenn seit diesem "
            "Zeitpunkt mehr als 24h vergangen sind, wird price_fetch_blocked "
            "gesetzt und ein Jira-Ticket angelegt (statt bei jedem einzelnen "
            "Fehlschlag)."
        ),
    )

    suspicious_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=(
            "Abgelehnter Kurs, der zu stark vom letzten current_price abweicht "
            "(Plausibilitäts-Check). Bleibt dieser Wert über "
            "suspicious_price_since hinweg >24h konsistent (statt bei jedem Lauf "
            "zufällig anders), gilt er als echter Kurssprung (Split, Rallye, "
            "Crash) statt als einmaliger Scraping-Fehler und wird automatisch "
            "übernommen."
        ),
    )
    suspicious_price_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Zeitpunkt, seit dem suspicious_price konsistent gemeldet wird.",
    )

    logo = models.URLField(
        blank=True,
        null=True,
        help_text="Logo-URL, z.B. https://s3-symbol-logo.tradingview.com/iberdrola--big.svg"
    )

    holdings_reference = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='holdings_reference_for',
        limit_choices_to={'asset_class__in': [AssetClass.ETF, AssetClass.FOND]},
        help_text=(
            "Für update_etf_holdings (Aktien-Look-Through) stattdessen die JustETF-Seite "
            "DIESES Fonds für die Holdings-Daten verwenden — z.B. 'iShares Core MSCI World' "
            "(IE00B4L5Y983) als gemeinsame Referenz für andere Anbieter, die denselben Index "
            "('MSCI World') abbilden. Nur für Fonds mit WIRKLICH identischem Index sinnvoll — "
            "z.B. NICHT für einen MSCI-ACWI-Fonds, der zusätzlich Emerging Markets enthält. "
            "Leer = eigene JustETF-Seite verwenden."
        ),
    )

    extend_etf = models.CharField(
        max_length=20,
        choices=EtfExtendSource.choices,
        blank=True,
        default='',
        verbose_name="Extend ETF",
        help_text=(
            "Für update_etf_holdings: zusätzlich zu den JustETF-Top-10 die übrigen Positionen "
            "(noch kein Mapping für diesen Fonds) von einer externen Quelle nachtragen (DAX: "
            "Wikipedia, MSCI World: companiesmarketcap.com) — nur für Aktien, die im System "
            "bereits bekannt sind (direkt gehalten oder bereits über einen anderen Fonds "
            "erfasst; Namensabgleich, diese Quellen führen keine ISIN). Nur bei einem echten "
            "Tracker des jeweiligen Index setzen. Nur bei asset_class=ETF erlaubt."
        ),
    )

    ark_ticker = models.CharField(
        max_length=10,
        blank=True,
        default='',
        verbose_name="ARK-Ticker",
        help_text=(
            "Für update_etf_holdings: statt der JustETF-Top-10 die vollständige, "
            "tagesaktuelle Holdings-Liste direkt von ARK Invest verwenden (z.B. 'ARKK' für "
            "den ARK Innovation ETF) — liefert CUSIP, woraus die ISIN berechnet wird, kein "
            "Namensabgleich nötig. Nur sinnvoll für Fonds, die tatsächlich einen ARK-ETF "
            "1:1 abbilden/nachbilden (z.B. 'ARK Innovation (Acc)'). Nur bei asset_class=ETF "
            "erlaubt."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.extend_etf and self.asset_class != AssetClass.ETF:
            raise ValidationError({
                'extend_etf': "extend_etf darf nur bei asset_class=ETF gesetzt werden.",
            })
        if self.ark_ticker and self.asset_class != AssetClass.ETF:
            raise ValidationError({
                'ark_ticker': "ark_ticker darf nur bei asset_class=ETF gesetzt werden.",
            })

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
        validators=[MinValueValidator(Decimal('0'))],
        help_text=(
            "Anzahl gehaltener Anteile (auch Bruchteile möglich). "
            "0 = Dummy-Eintrag für eine Aktie, die nur über einen Fonds "
            "(FondHolding-Mapping) gehalten wird, nicht direkt."
        )
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
        # Preis-Alarme prüfen (Kreuzung des Zielkurses seit dem letzten Kurs)
        self._check_price_alarms(self.current_price)
        # Trailing-Stop-Loss prüfen (Referenzhoch nachziehen, Auslösen bei Unterschreiten)
        self._check_trailing_stops(self.current_price)

    def _update_week52(self, price):
        """Prüft ob der neue Kurs ein neues 52W-Hoch oder -Tief darstellt."""
        try:
            r = self.asset.week52
        except Exception:
            return  # Noch kein Range-Eintrag → nichts zu tun

        if r.skip_yahoo:
            return  # Blacklist-Eintrag → nicht anfassen

        if r.is_expired():
            r.delete()
            return

        if r.week52_high is None or r.week52_low is None:
            return  # Noch keine Werte (skip_yahoo war mal True oder Fetch ausstehend)

        # Beide Werte sind jetzt in EUR → direkter Vergleich möglich
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

    def _check_price_alarms(self, price):
        """
        Prüft aktive PriceAlarm-Einträge des Assets auf Kreuzung des Zielkurses
        seit dem vorherigen gespeicherten Kurs:
          a) vorher < Ziel, jetzt >= Ziel  (Aufwärtskreuzung)
          b) vorher > Ziel, jetzt <= Ziel  (Abwärtskreuzung)
        Ohne einen vorherigen Kurs (erster Datenpunkt) kann keine Kreuzung
        erkannt werden. Ausgelöste Alarme werden deaktiviert.
        """
        previous = self.asset.prices.exclude(pk=self.pk).order_by('-timestamp').first()
        if previous is None:
            return

        prev_price = previous.current_price
        for alarm in self.asset.price_alarms.filter(is_active=True):
            target = alarm.target_price
            if prev_price < target and price >= target:
                direction = PriceAlarmEvent.Direction.UP
            elif prev_price > target and price <= target:
                direction = PriceAlarmEvent.Direction.DOWN
            else:
                continue

            event = PriceAlarmEvent.objects.create(
                alarm=alarm,
                asset=self.asset,
                target_price=target,
                direction=direction,
                previous_price=prev_price,
                triggered_price=price,
            )
            alarm.is_active = False
            alarm.save(update_fields=['is_active'])

            # Sofort-Versand nur als Optimierung, falls dieser Prozess Telegram
            # konfiguriert hat (z.B. die Live-App). Prozesse ohne Konfiguration
            # (z.B. update_prices auf GitHub Actions) lassen notified_at NULL —
            # der notify-price-alarms-Endpoint holt das dann nach.
            if send_telegram_message(format_price_alarm_message(event), trigger="price_alarm"):
                event.notified_at = timezone.now()
                event.save(update_fields=['notified_at'])

    def _check_trailing_stops(self, price):
        """
        Zieht das Referenzhoch eines aktiven TrailingStopLoss für dieses Asset
        nach (nur aufwärts) und löst aus, sobald der Kurs trail_percent unter
        das Referenzhoch fällt. Nichts zu tun, wenn kein Bestand oder kein
        Trailing-Stop für diesen Bestand existiert.
        """
        holding = self.asset.holdings.first()
        if holding is None:
            return
        try:
            tsl = holding.trailing_stop_loss
        except TrailingStopLoss.DoesNotExist:
            return
        if not tsl.is_active:
            return

        update_fields = []
        if price > tsl.reference_price:
            tsl.reference_price = price
            update_fields.append('reference_price')

        if price <= tsl.trigger_price:
            event = TrailingStopEvent.objects.create(
                trailing_stop=tsl,
                asset=self.asset,
                trail_percent=tsl.trail_percent,
                reference_price=tsl.reference_price,
                triggered_price=price,
            )
            tsl.is_active = False
            update_fields.append('is_active')

            # Sofort-Versand nur als Optimierung — siehe _check_price_alarms oben.
            if send_telegram_message(format_trailing_stop_message(event), trigger="trailing_stop"):
                event.notified_at = timezone.now()
                event.save(update_fields=['notified_at'])

        if update_fields:
            tsl.save(update_fields=update_fields)

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
    52-Wochen-Hoch und -Tief für ein Asset, alle Werte in EUR.
    Wird lazy über die Yahoo-Finance-API befüllt und in der DB gecacht.
    Ablauf: fetched_at älter als TTL → Datensatz löschen und neu holen.
    """
    asset = models.OneToOneField(
        Asset,
        on_delete=models.CASCADE,
        related_name='week52',
    )
    skip_yahoo = models.BooleanField(
        default=False,
        help_text="True = Yahoo-Abfrage sperren (z.B. ETFs ohne sinnvolle 52W-Daten). "
                  "Wird bei Refresh nicht gelöscht.",
    )
    week52_high = models.DecimalField(
        max_digits=12, decimal_places=4,
        null=True, blank=True,
        help_text="52-Wochen-Hoch in EUR",
    )
    week52_high_date = models.DateField(
        null=True, blank=True,
        help_text="Datum, an dem das 52-Wochen-Hoch zuletzt aktualisiert wurde",
    )
    week52_low = models.DecimalField(
        max_digits=12, decimal_places=4,
        null=True, blank=True,
        help_text="52-Wochen-Tief in EUR",
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
        if self.skip_yahoo:
            return f"{self.asset.symbol or self.asset.isin}: (Yahoo gesperrt)"
        return f"{self.asset.symbol or self.asset.isin}: H={self.week52_high} T={self.week52_low}"

    def is_expired(self) -> bool:
        """True wenn die Daten abgelaufen sind.
        - Ohne Datum (Yahoo liefert keins): TTL aus FinConfig (default 7 Tage)
        - Mit Datum (von Price.save() gesetzt): nach 52 Wochen
        """
        from datetime import timedelta
        if self.week52_high_date is None or self.week52_low_date is None:
            ttl_days = FinConfig.get().week52_no_date_ttl_days
            return self.fetched_at < timezone.now() - timedelta(days=ttl_days)
        return self.fetched_at < timezone.now() - timedelta(weeks=52)


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


class PriceAlarm(models.Model):
    """
    Vom Nutzer gesetzter Ziel-Kurswert für ein Asset. Löst aus, sobald der
    Kurs die Schwelle in eine der beiden Richtungen kreuzt (siehe
    Price._check_price_alarms), und wird danach automatisch deaktiviert.
    """
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='price_alarms',
    )
    target_price = models.DecimalField(
        max_digits=12, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text="Kurswert, bei dessen Über- oder Unterschreiten der Alarm auslöst.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Preis-Alarm"
        verbose_name_plural = "Preis-Alarme"
        ordering = ['asset__name', 'target_price']

    def __str__(self):
        status = "aktiv" if self.is_active else "ausgelöst"
        return f"{self.asset.symbol or self.asset.isin} @ {self.target_price} ({status})"


class PriceAlarmEvent(models.Model):
    """
    Protokoll eines ausgelösten PriceAlarm. Bleibt auch erhalten, wenn der
    zugehörige Alarm später gelöscht wird (alarm dann NULL).
    """
    class Direction(models.TextChoices):
        UP   = 'up',   'Aufwärts gekreuzt'
        DOWN = 'down', 'Abwärts gekreuzt'

    alarm = models.ForeignKey(
        PriceAlarm,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='events',
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='price_alarm_events',
    )
    target_price = models.DecimalField(max_digits=12, decimal_places=4)
    direction = models.CharField(max_length=4, choices=Direction.choices)
    previous_price = models.DecimalField(max_digits=12, decimal_places=4)
    triggered_price = models.DecimalField(max_digits=12, decimal_places=4)
    triggered_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "Zeitpunkt, an dem die Telegram-Nachricht erfolgreich verschickt wurde. "
            "NULL = noch ausstehend — wird vom notify-price-alarms-Endpoint nachgeholt "
            "(z.B. wenn das Event aus einem Prozess ohne Telegram-Konfiguration entstand, "
            "etwa dem update_prices-Lauf auf GitHub Actions)."
        ),
    )

    class Meta:
        verbose_name = "Preis-Alarm-Ereignis"
        verbose_name_plural = "Preis-Alarm-Ereignisse"
        ordering = ['-triggered_at']

    def __str__(self):
        return f"{self.asset.symbol or self.asset.isin}: {self.get_direction_display()} {self.target_price} ({self.triggered_at:%Y-%m-%d %H:%M})"


def format_price_alarm_message(event: "PriceAlarmEvent") -> str:
    """Telegram-Text für ein PriceAlarmEvent — geteilt zwischen Sofort-Versand
    (Price._check_price_alarms) und dem notify-price-alarms-Nachhol-Endpoint."""
    emoji = "📈" if event.direction == PriceAlarmEvent.Direction.UP else "📉"
    arrow = "über" if event.direction == PriceAlarmEvent.Direction.UP else "unter"
    return (
        f"{emoji} Preis-Alarm: {event.asset.name} ({event.asset.symbol or event.asset.isin}) "
        f"{arrow} Zielkurs {event.target_price} — {event.previous_price} → {event.triggered_price}"
    )


class TrailingStopLoss(models.Model):
    """
    Trailing-Stop-Loss für einen Bestand (Holdings). Der Referenzwert
    (reference_price) beginnt beim Kurs bei Aktivierung und steigt mit neuen
    Kurshochs mit, fällt aber nie. Löst aus, sobald der Kurs um trail_percent
    unter den Referenzwert fällt (siehe Price._check_trailing_stops), und wird
    danach automatisch deaktiviert.
    """
    holdings = models.OneToOneField(
        Holdings,
        on_delete=models.CASCADE,
        related_name='trailing_stop_loss',
    )
    trail_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal('10.00'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('99.99'))],
        help_text="Prozentualer Abstand zum Referenzhoch, bei dessen Unterschreiten der Alarm auslöst.",
    )
    activated_price = models.DecimalField(
        max_digits=12, decimal_places=4,
        help_text="Kurs bei Aktivierung — unveränderlicher Startwert des Referenzhochs.",
    )
    reference_price = models.DecimalField(
        max_digits=12, decimal_places=4,
        help_text="Aktuelles Referenzhoch seit Aktivierung. Steigt mit neuen Kurshochs, fällt nie.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Trailing Stop-Loss"
        verbose_name_plural = "Trailing Stop-Losses"

    def __str__(self):
        status = "aktiv" if self.is_active else "ausgelöst"
        return f"{self.holdings.asset.symbol or self.holdings.asset.isin}: -{self.trail_percent}% ab {self.reference_price} ({status})"

    @property
    def trigger_price(self):
        return (self.reference_price * (Decimal('100') - self.trail_percent) / Decimal('100')).quantize(Decimal('0.0001'))


class TrailingStopEvent(models.Model):
    """
    Protokoll eines ausgelösten TrailingStopLoss. Bleibt auch erhalten, wenn
    der zugehörige Trailing-Stop später gelöscht wird (trailing_stop dann NULL).
    """
    trailing_stop = models.ForeignKey(
        TrailingStopLoss,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='events',
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name='trailing_stop_events',
    )
    trail_percent = models.DecimalField(max_digits=5, decimal_places=2)
    reference_price = models.DecimalField(max_digits=12, decimal_places=4)
    triggered_price = models.DecimalField(max_digits=12, decimal_places=4)
    triggered_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(
        null=True, blank=True,
        help_text=(
            "Zeitpunkt, an dem die Telegram-Nachricht erfolgreich verschickt wurde. "
            "NULL = noch ausstehend — wird vom notify-price-alarms-Endpoint nachgeholt."
        ),
    )

    class Meta:
        verbose_name = "Trailing-Stop-Ereignis"
        verbose_name_plural = "Trailing-Stop-Ereignisse"
        ordering = ['-triggered_at']

    def __str__(self):
        return (
            f"{self.asset.symbol or self.asset.isin}: Trailing-Stop -{self.trail_percent}% "
            f"ab {self.reference_price} @ {self.triggered_price} ({self.triggered_at:%Y-%m-%d %H:%M})"
        )


def format_trailing_stop_message(event: "TrailingStopEvent") -> str:
    """Telegram-Text für ein TrailingStopEvent — geteilt zwischen Sofort-Versand
    (Price._check_trailing_stops) und dem notify-price-alarms-Nachhol-Endpoint."""
    return (
        f"🛑 Trailing-Stop: {event.asset.name} ({event.asset.symbol or event.asset.isin}) "
        f"-{event.trail_percent}% unter Hoch {event.reference_price} ausgelöst — Kurs {event.triggered_price}"
    )


class NewsArticle(models.Model):
    """
    Nachrichtenartikel zu einem gehaltenen Unternehmen (News-Feed,
    /fintech/news-feed/). Wird periodisch vom update_news-Command befüllt
    (Yahoo Finance + Google News RSS) — bewusst gecacht statt live beim
    Seitenaufruf abgerufen, sonst würde jeder Page-Load Dutzende externe
    Requests auslösen.
    """
    class Provider(models.TextChoices):
        YAHOO  = 'yahoo',        'Yahoo Finance'
        GOOGLE = 'google_news',  'Google News'

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='news_articles',
        help_text="NULL bei manuell erfassten Fonds-Positionen ohne Asset-Match (siehe company_name).",
    )
    company_name = models.CharField(max_length=200, help_text="Denormalisiert, auch wenn asset gesetzt ist.")
    title = models.CharField(max_length=500)
    link = models.URLField(max_length=2048, unique=True)
    source = models.CharField(max_length=100, blank=True)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    thumbnail_url = models.URLField(max_length=2048, blank=True, null=True)
    published_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "News-Artikel"
        verbose_name_plural = "News-Artikel"
        ordering = ['-published_at', '-fetched_at']
        indexes = [
            models.Index(fields=['-published_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.source or self.get_provider_display()})"


class FondHolding(models.Model):
    """
    Manuell gepflegtes Mapping: Welche Einzelaktien hält ein Fonds/ETF, und mit
    welchem Gewicht? Basis für den Look-Through-Wert auf der Aktien-Übersicht
    (/fintech/overall-stocks/) — verrechnet direkt gehaltene Aktien mit dem
    über Fonds gehaltenen Anteil.
    """
    fund = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        related_name='fund_holdings',
        limit_choices_to={'asset_class__in': [AssetClass.ETF, AssetClass.FOND]},
        help_text="Der Fonds/ETF (muss als Asset existieren, i.d.R. eine deiner Holdings)",
    )
    holding = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        related_name='held_by_funds',
        limit_choices_to={'asset_class': AssetClass.STOCK},
        help_text="Die Einzelaktie, die der Fonds hält (muss als Asset existieren)",
    )
    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Gewichtung der Aktie im Fonds in Prozent, z.B. 4.250 für 4,25%",
    )

    class Meta:
        verbose_name = "Fonds-Holding"
        verbose_name_plural = "Fonds-Holdings"
        unique_together = ['fund', 'holding']
        ordering = ['fund__name', '-percentage']

    def __str__(self):
        return f"{self.fund.name} → {self.holding.name} ({self.percentage}%)"


class ManualFondHolding(models.Model):
    """
    Halb-manuell gepflegte Fonds-Holdings — für aktiv gemanagte Fonds ohne
    strukturierte Datenquelle (z.B. aus einem Factsheet abgetippt). Anders
    als FondHolding braucht die Position keine ISIN/kein existierendes
    Asset (holding_name ist Freitext) — die Look-Through-View versucht zur
    Anzeige einen Namensabgleich gegen bekannte Assets, zeigt aber auch ohne
    Treffer eine Zeile mit dem eingegebenen Namen.

    Hat ein Fonds hier mindestens einen Eintrag, wird NUR diese Tabelle für
    seinen Beitrag zu "Akt. Wert Fonds" verwendet (FondHolding-Einträge für
    diesen Fonds werden ignoriert). Hat er keinen Eintrag, greift das
    bisherige FondHolding-Verhalten unverändert.
    """
    fund = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        related_name='manual_fund_holdings',
        limit_choices_to={'asset_class__in': [AssetClass.ETF, AssetClass.FOND]},
        help_text="Der Fonds/ETF (muss als Asset existieren, i.d.R. eine deiner Holdings)",
    )
    holding_name = models.CharField(
        max_length=200,
        help_text="Name der Position, z.B. aus einem Factsheet abgetippt (keine ISIN nötig).",
    )
    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Gewichtung in Prozent, z.B. 10.100 für 10,1%",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Manuelles Fonds-Holding"
        verbose_name_plural = "Manuelle Fonds-Holdings"
        ordering = ['fund__name', '-percentage']

    def __str__(self):
        return f"{self.fund.name} → {self.holding_name} ({self.percentage}%)"


class NameAlias(models.Model):
    """
    Manuell gepflegte Synonym-Tabelle für den Namensabgleich in
    fintech.apis.services.name_matching (DAX-/MSCI-World-Tail-Erweiterung,
    ManualFondHolding) — für die wenigen Fälle, in denen externe Quelle und
    im System gespeicherter Name KEIN gemeinsames Wort haben (z.B. "BMW" vs.
    "BAY.MOTOREN WERKE AG ST") oder unterschiedlich zusammengeschrieben sind
    (z.B. "Exxonmobil" vs. "Exxon Mobil"). external_name wird normalisiert
    mit dem gespeicherten Namen verglichen; bei Treffer werden stattdessen
    die normalisierten Wörter von search_term als Suchbegriff verwendet.
    """
    external_name = models.CharField(
        max_length=100,
        unique=True,
        help_text='Name, wie er in der externen Quelle steht, z.B. "BMW".',
    )
    search_term = models.CharField(
        max_length=100,
        help_text=(
            'Ersatz-Suchbegriff, dessen Wörter stattdessen gegen den gehaltenen Namen '
            'geprüft werden, z.B. "Motoren Werke". Bewusst knapp halten, damit es auch mit '
            'unterschiedlich abgekürzten Schreibweisen im eigenen Bestand funktioniert.'
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Namens-Synonym"
        verbose_name_plural = "Namens-Synonyme"
        ordering = ['external_name']

    def __str__(self):
        return f"{self.external_name} → {self.search_term}"
