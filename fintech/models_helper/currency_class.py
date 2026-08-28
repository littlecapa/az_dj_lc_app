from django.db import models
import re

class CurrencyClass(models.TextChoices):  # FIX: TextChoices statt IntegerChoices (ISO-Codes sind Strings)
    EUR = 'EUR', 'EUR'
    USD = 'USD', 'USD'
    CHF = 'CHF', 'CHF'
    GBP = 'GBP', 'GBP'
    GBp = 'GBp', 'GBp'
    JPY = 'JPY', 'JPY'
    NOK = 'NOK', 'NOK'
    CAD = 'CAD', 'CAD'
    DKK = 'DKK', 'DKK'
    SEK = 'SEK', 'SEK'
    AUD = 'AUD', 'AUD'
    KRW = 'KRW', 'KRW'
    CNY = 'CNY', 'CNY'
    HKD = 'HKD', 'HKD'
    MXN = 'MXN', 'MXN'
    PLN = 'PLN', 'PLN'
    ZAR = 'ZAR', 'ZAR'
    ZAc = 'ZAc', 'ZAc'
    TWD = 'TWD', 'TWD'  # nicht in frankfurter.dev — CurrencyProxy nutzt Alpha Vantage als Fallback

    @classmethod
    def get_currency_pattern(cls):
        """Gibt Regex-Pattern für alle Currency-Codes zurück."""
        return r"(" + "|".join(re.escape(code) for code in cls.values) + r")"

