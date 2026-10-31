from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

RATING_VALIDATORS = [MinValueValidator(1), MaxValueValidator(10)]
RATING_HELP = '1–10, 10 = sehr gut'


class Category(models.Model):
    """Feste Auswahlliste (z. B. Genre bei Artists), Pflege im Admin."""
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Kategorie'
        verbose_name_plural = 'Kategorien'

    def __str__(self):
        return self.name


class Venue(models.Model):
    name = models.CharField(max_length=200, unique=True)
    country = models.CharField('Land', max_length=100)
    info = models.TextField(blank=True)
    picture_url = models.URLField('Link zum Bild', max_length=500, blank=True)
    rating = models.PositiveSmallIntegerField(default=8, validators=RATING_VALIDATORS, help_text=RATING_HELP)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Artist(models.Model):
    name = models.CharField(max_length=200, unique=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name='artists',
                                 verbose_name='Kategorie')
    rating = models.PositiveSmallIntegerField(default=8, validators=RATING_VALIDATORS, help_text=RATING_HELP)
    info = models.TextField(blank=True)
    song_url = models.URLField('Link zum Song', max_length=500, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UpcomingEvent(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name='events')
    artist = models.ForeignKey(Artist, on_delete=models.PROTECT, related_name='events')
    date = models.DateField('Datum')
    info = models.TextField(blank=True)
    ticket_url = models.URLField('Link zu Tickets', max_length=500, blank=True)

    class Meta:
        ordering = ['date', 'venue__name']
        verbose_name = 'Upcoming Event'
        constraints = [
            models.UniqueConstraint(fields=['venue', 'artist', 'date'], name='leisure_unique_event'),
        ]

    def __str__(self):
        return f'{self.artist} @ {self.venue} ({self.date:%d.%m.%Y})'


class Suggestion(models.Model):
    """Von Claude vorgeschlagener neuer Eintrag. Bewertung im Formular: Daumen hoch + Rating → wird übernommen
    (accepted), Daumen runter → rejected = Blacklist, wird nie wieder vorgeschlagen. Offene bleiben pending."""

    class Kind(models.TextChoices):
        ARTIST = 'artist', 'Artist'
        VENUE = 'venue', 'Venue'
        EVENT = 'event', 'Event'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Offen'
        ACCEPTED = 'accepted', 'Übernommen'
        REJECTED = 'rejected', 'Abgelehnt (Blacklist)'

    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name='suggestions',
                                 verbose_name='Kategorie')
    info = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True, help_text='Weitere Felder je Art, z. B. song_url')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING_VALIDATORS, help_text=RATING_HELP)
    created_at = models.DateTimeField('Vorgeschlagen am', auto_now_add=True)
    decided_at = models.DateTimeField('Entschieden am', null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Vorschlag'
        verbose_name_plural = 'Vorschläge'
        constraints = [models.UniqueConstraint(fields=['kind', 'name'], name='leisure_unique_suggestion')]

    def __str__(self):
        return f'{self.get_kind_display()}: {self.name} ({self.get_status_display()})'
