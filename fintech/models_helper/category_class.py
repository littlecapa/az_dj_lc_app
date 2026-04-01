from django.db import models

class CategoryClass(models.IntegerChoices):
        BASIS_INVESTMENT = 1, 'Basis Investment'
        DIVIDENDE = 2, 'Dividende'
        D_EU = 3, 'D/EU'
        US_TECH = 4, 'US Tech'
        WORLD_TECH = 5, 'World Tech'
        COMPOUNDER = 6, 'Compounder'
        DEFENCE = 7, 'Defence'
        ROBOTICS = 8, 'Robotics'
        CYBERSECURITY = 9, 'Cybersecurity'
        SOFTWARE = 10, 'Software'
        HEALTHCARE = 11, 'Healthcare'
        AI_INPUT = 12, 'AI Input'
        FINANCE = 13, 'Finance'
        CRYPTO = 14, 'Crypto'
        SONSTIGES = 99, 'Sonstiges'