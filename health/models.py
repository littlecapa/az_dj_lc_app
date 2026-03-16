from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

class BloodPressure(models.Model):
    datum_zeit = models.DateTimeField('Datum & Uhrzeit', help_text='Morgen/Abend + Uhrzeit', default=timezone.now)
    systolisch = models.PositiveIntegerField(
        'Systolisch (oberer Wert)',
        validators=[MinValueValidator(60), MaxValueValidator(300)]
    )
    diastolisch = models.PositiveIntegerField(
        'Diastolisch (unterer Wert)',
        validators=[MinValueValidator(40), MaxValueValidator(200)]
    )
    herzschlag = models.PositiveIntegerField(
        'Herzschlag (bpm)',
        validators=[MinValueValidator(30), MaxValueValidator(250)]
    )
    info = models.CharField('Info-Notiz', max_length=256, blank=True, help_text='Zusätzliche Notizen (max. 256 Zeichen)')
    
    class Meta:
        verbose_name = 'Blutdruckmessung'
        verbose_name_plural = 'Blutdruckmessungen'
        ordering = ['-datum_zeit']  # Neueste oben
    
    def __str__(self):
        local_dt = timezone.localtime(self.datum_zeit)
        return f"{local_dt.strftime('%d.%m %H:%M')}: {self.systolisch}/{self.diastolisch} ({self.herzschlag} bpm)"