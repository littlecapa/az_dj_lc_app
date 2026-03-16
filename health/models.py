from django.db import models

class BloodPressure(models.Model):
    datum = models.DateField('Datum', help_text='Morgen oder Abend')
    systolisch = models.PositiveIntegerField('Systolisch (oberer Wert)')
    diastolisch = models.PositiveIntegerField('Diastolisch (unterer Wert)')
    herzschlag = models.PositiveIntegerField('Herzschlag (bpm)')
    info = models.BooleanField('Info-Flag', default=False, help_text='Messwerte-Info markieren')
    
    class Meta:
        verbose_name = 'Blutdruckmessung'
        verbose_name_plural = 'Blutdruckmessungen'
        ordering = ['-datum']  # Neueste oben
    
    def __str__(self):
        return f"{self.datum}: {self.systolisch}/{self.diastolisch} ({self.herzschlag} bpm)"
