from django.contrib import admin
from .models import BloodPressure

@admin.register(BloodPressure)
class BloodPressureAdmin(admin.ModelAdmin):
    list_display = ['datum_zeit', 'systolisch', 'diastolisch', 'herzschlag', 'info']
    list_filter = ['datum_zeit', 'info__isnull']
    search_fields = ['datum_zeit', 'info']
    date_hierarchy = 'datum_zeit'
