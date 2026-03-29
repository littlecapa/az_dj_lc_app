"""
Eigene Template-Filter für deutsches Zahlenformat.

Verwendung im Template:
    {% load de_format %}

    {{ wert|de_decimal:2 }}      →  1.234,56
    {{ wert|de_decimal:4 }}      →  1.234,5678
    {{ wert|de_percent:1 }}      → +12,3 %  /  -3,4 %
    {{ wert|de_currency:2 }}     →  1.234,56 €
"""

from django import template
from decimal import Decimal, InvalidOperation
from typing import Optional

register = template.Library()


def _to_decimal(value) -> Optional[Decimal]:
    """Konvertiert beliebige Eingaben sicher zu Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_de(value: Decimal, decimal_places: int) -> str:
    """Formatiert Decimal als deutsches Zahlenformat (Punkt=Tausender, Komma=Dezimal)."""
    rounded = round(value, decimal_places)
    # Python-Format mit Tausenderpunkt
    formatted = f"{rounded:,.{decimal_places}f}"
    # Amerikanisch → Deutsch: , und . tauschen
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def de_decimal(value, decimal_places=2):
    """Zahl im deutschen Format: 1.234,56"""
    dec = _to_decimal(value)
    if dec is None:
        return "—"
    return _format_de(dec, int(decimal_places))


@register.filter
def de_percent(value, decimal_places=1):
    """Prozent mit Vorzeichen im deutschen Format: +12,3 % / -3,4 %"""
    dec = _to_decimal(value)
    if dec is None:
        return "—"
    sign = "+" if dec >= 0 else ""
    return f"{sign}{_format_de(dec, int(decimal_places))} %"


@register.filter
def de_currency(value, decimal_places=2):
    """Betrag in Euro im deutschen Format: 1.234,56 €"""
    dec = _to_decimal(value)
    if dec is None:
        return "—"
    return f"{_format_de(dec, int(decimal_places))} €"
