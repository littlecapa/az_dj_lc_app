from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ContactForm
from .models import ContactMessage
from django.contrib.auth.decorators import user_passes_test
from .models import HistChessMagazine

def historical_chess_mags(request):
    # Nur aktive Magazine holen
    active_mags = HistChessMagazine.objects.filter(is_active=True)

    # Gruppierung für das Template vorbereiten
    context = {
        'german_mags': active_mags.filter(language='German'),
        'english_mags': active_mags.filter(language='English'),
        'spanish_mags': active_mags.filter(language='Spanish'),
        'other_mags': active_mags.filter(language='Other'),
    }
    return render(request, 'homepage/historical-chess-mags.html', context)

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

# Prüffunktion: Ist der User ein Admin?
def is_admin(user):
    return user.is_authenticated and user.is_superuser

@user_passes_test(is_admin)
def monitoring_view(request):
    # Zähle alle ungelesenen Nachrichten
    # Annahme: Ihr Model hat ein BooleanField 'is_read' oder ähnlich.
    # Falls nicht, müssen wir das anpassen (z.B. status='new').
    unread_count = ContactMessage.objects.filter(is_read=False).count()

    context = {
        'unread_count': unread_count,
    }
    return render(request, 'homepage/monitoring.html', context)