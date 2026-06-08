"""Hilfsfunktionen für Währungsumrechnung."""
from decimal import Decimal


def to_eur(value, currency: str) -> Decimal:
    """Konvertiert einen Wert in EUR. Gibt Decimal zurück."""
    from fintech.apis.services.exchange_rate_proxy import CurrencyProxy
    dec = Decimal(str(value))
    if currency.upper() == 'EUR':
        return dec
    rate = CurrencyProxy().get_rate(currency)
    return (dec / Decimal(str(rate))).quantize(Decimal('0.0001'))
