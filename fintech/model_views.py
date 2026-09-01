from django.db.models import F, Sum, ExpressionWrapper, DecimalField, Value, OuterRef, Subquery
from django.db.models.functions import Coalesce, NullIf
from django.db import models
from django.utils import timezone
from decimal import Decimal
from .models import Asset, Holdings, Price

D = DecimalField(max_digits=20, decimal_places=4)  # shorthand


class PortfolioSummaryQuerySet(models.QuerySet):

    def summary(self):
        # effective_price: current_price wenn vorhanden, sonst average_purchase_price
        # Coalesce löst das Aggregat-in-Aggregat Problem sauber auf SQL-Ebene
        effective_price = Coalesce(
            F('current_price'),
            F('holdings__average_purchase_price'),
            output_field=D,
        )

        cost_basis = ExpressionWrapper(
            F('holdings__quantity') * F('holdings__average_purchase_price'),
            output_field=D,
        )
        market_value = ExpressionWrapper(
            F('holdings__quantity') * effective_price,
            output_field=D,
        )

        return (
            self
            .filter(holdings__quantity__gt=Value(Decimal('0'), output_field=D))
            .annotate(
                total_quantity   = Sum('holdings__quantity'),
                purchase_price   = Sum(cost_basis),
                current_value    = Sum(market_value),
                delta_abs        = ExpressionWrapper(Sum(market_value) - Sum(cost_basis), output_field=D),
                delta_perc       = ExpressionWrapper(
                    (Sum(market_value) / NullIf(Sum(cost_basis), Value(Decimal('0'), output_field=D)) - Value(Decimal('1'), output_field=D)) * Value(Decimal('100'), output_field=D),
                    output_field=D,
                ),
            )
            .order_by('-current_value')
        )


class PortfolioSummaryManager(models.Manager):
    def get_queryset(self):
        return PortfolioSummaryQuerySet(Asset, using=self._db)

    def portfolio(self):
        today = timezone.now().date()

        yesterday_price_sq = Price.objects.filter(
            asset=OuterRef('pk'),
            timestamp__date__lt=today,
        ).order_by('-timestamp').values('current_price')[:1]

        return (
            self.get_queryset()
            .summary()
            .annotate(
                yesterday_price=Subquery(yesterday_price_sq, output_field=D),
                delta_perc_yesterday=ExpressionWrapper(
                    (
                        F('current_price')
                        / NullIf(F('yesterday_price'), Value(Decimal('0'), output_field=D))
                        - Value(Decimal('1'), output_field=D)
                    ) * Value(Decimal('100'), output_field=D),
                    output_field=D,
                ),
            )
            .order_by(F('delta_perc_yesterday').desc(nulls_last=True))
            .values(
                'name', 'isin', 'symbol',
                'asset_class',
                'total_quantity', 'purchase_price',
                'current_value', 'delta_abs', 'delta_perc',
                'delta_perc_yesterday',
                'holdings__not_for_sale',
                'holdings__stake_recovered',
            )
        )


class PortfolioSummary(models.Model):
    """Unmanaged proxy — nur für Django Admin, keine eigene DB-Tabelle."""
    name           = models.CharField(max_length=200)
    isin           = models.CharField(max_length=12)
    asset_class    = models.CharField(max_length=10)   # war category_display — nicht im Asset-Model
    total_quantity = models.DecimalField(max_digits=20, decimal_places=6)
    purchase_price = models.DecimalField(max_digits=20, decimal_places=2)
    current_value  = models.DecimalField(max_digits=20, decimal_places=2)
    delta_abs      = models.DecimalField(max_digits=20, decimal_places=2)
    delta_perc     = models.DecimalField(max_digits=10, decimal_places=2)

    objects = PortfolioSummaryManager()

    class Meta:
        managed = False
        verbose_name = "Portfolio Position"
        verbose_name_plural = "Portfolio Übersicht"

    def __str__(self):
        return f"{self.name}: {self.current_value:.0f}€ (Δ{self.delta_perc:+.1f}%)"
