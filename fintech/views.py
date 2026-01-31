from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required

# Dieser Decorator schützt die View: Nur eingeloggte User kommen hier rein
@login_required
def fintech_home(request):
    return HttpResponse("Willkommen im geschützten Fintech-Bereich!")

# Beispiel für eine weitere geschützte View
@login_required
def fintech_dashboard(request):
    return render(request, 'fintech/dashboard.html')
