from django.db import models

class BloodPressure(models.Model):
    datum_zeit = models.DateTimeField('Datum & Uhrzeit', help_text='Morgen/Abend + Uhrzeit')
    systolisch = models.PositiveIntegerField('Systolisch (oberer Wert)')
    diastolisch = models.PositiveIntegerField('Diastolisch (unterer Wert)')
    herzschlag = models.PositiveIntegerField('Herzschlag (bpm)')
    info = models.CharField('Info-Notiz', max_length=256, blank=True, help_text='Zusätzliche Notizen (max. 256 Zeichen)')
    
    class Meta:
        verbose_name = 'Blutdruckmessung'
        verbose_name_plural = 'Blutdruckmessungen'
        ordering = ['-datum_zeit']  # Neueste oben
    
    def __str__(self):
        return f"{self.datum_zeit.strftime('%d.%m %H:%M')}: {self.systolisch}/{self.diastolisch} ({self.herzschlag} bpm)"
