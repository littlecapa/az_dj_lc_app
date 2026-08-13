from django.db import models


class EtfExtendSource(models.TextChoices):
    """Externe Quelle für die Positionen 11+ eines ETF in update_etf_holdings
    (JustETF liefert kostenlos nur Top 10)."""
    DAX        = 'DAX',        'DAX (Wikipedia)'
    MSCI_WORLD = 'MSCI_WORLD', 'MSCI World (companiesmarketcap.com)'
