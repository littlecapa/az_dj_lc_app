from django.db import models
from django.contrib.auth.models import User


class Rezept(models.Model):

    KATEGORIE_CHOICES = [
        ('fruehstueck', 'Frühstück'),
        ('suppen',      'Suppen'),
        ('vegetarisch', 'Vegetarisch'),
        ('fleisch',     'Fleisch & Fisch'),
        ('pasta',       'Pasta & Reis'),
        ('backen',      'Backen'),
        ('dessert',     'Desserts'),
        ('snacks',      'Snacks & Dips'),
        ('getraenke',   'Getränke'),
    ]

    AUFWAND_CHOICES = [
        ('niedrig', 'Niedrig'),
        ('mittel',  'Mittel'),
        ('hoch',    'Hoch'),
    ]

    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rezepte')
    name      = models.CharField(max_length=200)
    kategorie = models.CharField(max_length=50, choices=KATEGORIE_CHOICES, default='vegetarisch')
    aufwand   = models.CharField(max_length=20, choices=AUFWAND_CHOICES, default='niedrig')
    quelle    = models.CharField(max_length=100, blank=True)
    zutaten   = models.TextField(blank=True)        # Komma-getrennt
    zeit      = models.IntegerField(null=True, blank=True)  # Minuten
    saison    = models.CharField(max_length=50, default='Ganzjährig')
    notiz     = models.TextField(blank=True)
    link      = models.URLField(blank=True)
    liebling  = models.BooleanField(default=False)
    foto      = models.ImageField(upload_to='rezepte/', blank=True, null=True)
    erstellt  = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Rezept'
        verbose_name_plural = 'Rezepte'

    def __str__(self):
        return self.name
