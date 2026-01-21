from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ContactForm
from .models import ContactMessage

def index(request):
    return render(request, 'homepage/index.html')

def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            # Daten speichern
            ContactMessage.objects.create(
                name=form.cleaned_data['name'],
                email=form.cleaned_data['email'],
                message=form.cleaned_data['message']
            )
            
            # Erfolgsmeldung
            messages.success(request, 'Vielen Dank! Ihre Nachricht wurde gespeichert.')
            return redirect('homepage:contact')
    else:
        form = ContactForm()

    return render(request, 'homepage/contact.html', {'form': form})
