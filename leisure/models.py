from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

RATING_VALIDATORS = [MinValueValidator(1), MaxValueValidator(10)]
RATING_HELP = '1–10, 10 = sehr gut'


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

