from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def euro(value, signed=False):
    """Decimal → '1.234,56 €' (deutsches Format); mit Argument 'signed' immer mit Vorzeichen."""
    d = Decimal(value or 0).quantize(Decimal('0.01'))
    text = f'{abs(d):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    sign = '−' if d < 0 else ('+' if signed and d > 0 else '')
    return f'{sign}{text} €'
