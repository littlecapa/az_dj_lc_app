from django.views.generic import ListView
from django.http import HttpResponse
from .models import BloodPressure
from django.contrib.auth.mixins import LoginRequiredMixin 

import csv

class BloodPressureListView(LoginRequiredMixin, ListView):
    model = BloodPressure
    template_name = 'health/bp_list.html'
    context_object_name = 'messungen'
    ordering = ['-datum_zeit']

def get_export_csv(request):  # Diese Funktion ist OK, ohne as_view
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="blutdruck.csv"'
    writer = csv.writer(response)
    writer.writerow(['Datum/Uhrzeit', 'Systolisch', 'Diastolisch', 'Herzschlag', 'Info'])
    for messung in BloodPressure.objects.order_by('-datum_zeit'):
        writer.writerow([messung.datum_zeit.strftime('%d.%m.%Y %H:%M'), messung.systolisch, messung.diastolisch, 
                         messung.herzschlag, 'Ja' if messung.info else 'Nein'])
    return response
