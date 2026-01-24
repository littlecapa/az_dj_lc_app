from django.db import models
from django.utils import timezone

class ContactMessage(models.Model):
    name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False, verbose_name="Gelesen")

    class Meta:
        ordering = ['-created_at'] # Neueste Nachrichten zuerst
        verbose_name = "Kontakt-Nachricht"
        verbose_name_plural = "Kontakt-Nachrichten"

    def __str__(self):
        return f"Nachricht von {self.name} ({self.created_at.strftime('%d.%m.%Y')})"

from django.db import models

class HistChessMagazine(models.Model):
    LANGUAGE_CHOICES = [
        ('German', 'German'),
        ('English', 'English'),
        ('Spanish', 'Spanish'),
        ('Other', 'Other'),
    ]

    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES)
    name = models.CharField(max_length=100)  # Empfohlen: 100, da einige Titel lang sind
    link = models.URLField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Historical Chess Magazine"
        ordering = ['name']

