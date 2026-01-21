from django.shortcuts import render

def index(request):
    # Rendert jetzt das echte Template statt nur Text
    return render(request, 'homepage/index.html')
