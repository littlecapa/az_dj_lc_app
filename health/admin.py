from django.contrib import admin
from .models import BloodPressure

@admin.register(BloodPressure)
class BloodPressureAdmin(admin.ModelAdmin):
    list_display = ['datum_zeit', 'systolisch', 'diastolisch', 'herzschlag', 'has_info']
    list_filter = ['datum_zeit']  # info__isnull entfernt
    search_fields = ['datum_zeit', 'info']
    date_hierarchy = 'datum_zeit'

    def has_info(self, obj):
        return bool(obj.info.strip())
    has_info.short_description = 'Info vorhanden'
    has_info.boolean = True  # Checkbox-Spalte
