from django.views.generic import ListView
from django.http import HttpResponse
from .models import BloodPressure
from django.contrib.auth.mixins import LoginRequiredMixin 

import csv

class BloodPressureListView(LoginRequiredMixin, ListView):  # class, kein def!
    model = BloodPressure
    template_name = 'health/bp_list.html'
    context_object_name = 'messungen'

def get_export_csv(request):  # Diese Funktion ist OK, ohne as_view
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="blutdruck.csv"'
    writer = csv.writer(response)
    writer.writerow(['Datum', 'Systolisch', 'Diastolisch', 'Herzschlag', 'Info'])
    for messung in BloodPressure.objects.order_by('-datum'):
        writer.writerow([messung.datum, messung.systolisch, messung.diastolisch, 
                         messung.herzschlag, 'Ja' if messung.info else 'Nein'])
    return response
