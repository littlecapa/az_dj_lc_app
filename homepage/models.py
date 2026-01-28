from django.db import models
from django.utils import timezone
from django.db import models
from django.utils.text import slugify

class BlogPost(models.Model):
    # Datum
    date = models.DateField()
    
    # Überschrift (char(32) wie gewünscht - das ist recht kurz, passt aber für deine Beispiele)
    headline = models.CharField(max_length=64)
    
    # Summary (Text)
    summary = models.TextField()
    image_name = models.CharField(max_length=32)

    external_url = models.URLField(blank=True, null=True, help_text="If set, 'Read more' leads here (External). If empty, it loads the template based on the slug.")
    
    # Logic: This must match the filename in templates/homepage/blog/ (without .html)
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        # Wenn kein Link (Slug oder externe URL) gesetzt ist, generiere ihn aus der Headline
        if not self.slug and not self.external_url:
            self.slug = slugify(self.headline)[:50].rstrip('-')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.headline

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

