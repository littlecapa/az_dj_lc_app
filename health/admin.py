from django.contrib import admin
from .models import BloodPressure

@admin.register(BloodPressure)
class BloodPressureAdmin(admin.ModelAdmin):
    list_display = ['datum', 'systolisch', 'diastolisch', 'herzschlag', 'info']
    list_filter = ['datum', 'info']
    search_fields = ['datum']
    date_hierarchy = 'datum'
