from django.db import models


class AssetClass(models.TextChoices):
    STOCK      = 'STOCK',      'Aktie'
    ETF        = 'ETF',        'ETF'
    ETC        = 'ETC',        'ETC'
    CRYPTO     = 'CRYPTO',     'Kryptowährung'
    DERIVATIVE = 'DERIVATIVE', 'Derivat'
    FOND      = 'FOND', 'Fond'

    @classmethod
    def is_valid(cls, name: str) -> bool:
        return name in cls.values or name in cls.labels

    @classmethod
    def is_stock(cls, name: str) -> bool:
        return name in (cls.STOCK.value, cls.STOCK.label)

    @classmethod
    def is_etf(cls, name: str) -> bool:
        return name in (cls.ETF.value, cls.ETF.label)

    @classmethod
    def get_comdirect_config(cls) -> dict:
        """Gibt (url_template, req_id) pro AssetClass-Value zurück."""
        return _COMDIRECT_CONFIG

    @classmethod
    def comdirect_url(cls, value: str) -> str:
        return _COMDIRECT_CONFIG[value][0]

    @classmethod
    def comdirect_id(cls, value: str) -> str:
        return _COMDIRECT_CONFIG[value][1]
    
# Außerhalb der Klasse — wird NICHT als Enum-Member registriert
_COMDIRECT_CONFIG = {
    AssetClass.STOCK.value:      ("https://www.comdirect.de/inf/aktien/{isin}",      "com_stock"),
    AssetClass.ETF.value:        ("https://www.comdirect.de/inf/etfs/{isin}",         "com_etf"),
    AssetClass.ETC.value:        ("https://www.comdirect.de/inf/zertifikate/{isin}",  "com_etc"),
    AssetClass.CRYPTO.value:     ("https://www.comdirect.de/inf/zertifikate/{isin}",  "com_crypto"),
    AssetClass.DERIVATIVE.value: ("https://www.comdirect.de/inf/zertifikate/{isin}",  "com_cert"),
    AssetClass.FOND.value:       ("https://www.comdirect.de/inf/fonds/{isin}",        "com_fond"),
}