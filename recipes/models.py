from django.db import models
from django.contrib.auth.models import User


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'

    def __str__(self):
        return self.name


class Rezept(models.Model):

    KATEGORIE_CHOICES = [
        ('fruehstueck', 'Frühstück'),
        ('vorspeisen',  'Vorspeisen'),
        ('suppen',      'Suppen'),
        ('vegetarisch', 'Vegetarisch'),
        ('fleisch',     'Fleisch'),
        ('fisch',       'Fisch & Meeresfrüchte'),
        ('kartoffeln',  'Kartoffeln'),
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

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rezepte')
    name       = models.CharField(max_length=200)
    kategorie  = models.CharField(max_length=50, choices=KATEGORIE_CHOICES, default='vegetarisch')
    aufwand    = models.CharField(max_length=20, choices=AUFWAND_CHOICES, default='niedrig')
    quelle     = models.CharField(max_length=100, blank=True)
    zutaten    = models.TextField(blank=True)
    tags       = models.ManyToManyField(Tag, blank=True, related_name='rezepte')
    notiz      = models.TextField(blank=True, verbose_name='Zubereitung')
    link       = models.URLField(blank=True)
    liebling   = models.BooleanField(default=False)
    foto_url   = models.URLField(
        blank=True, null=True,
        verbose_name='Foto-URL',
        help_text='Direkter Bild-Link, z.B. Google Drive: https://drive.google.com/uc?id=FILE_ID'
    )
    foto       = models.ImageField(upload_to='rezepte/', blank=True, null=True)
    erstellt   = models.DateTimeField(auto_now_add=True)
    geaendert  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Rezept'
        verbose_name_plural = 'Rezepte'

    def __str__(self):
        return self.name
