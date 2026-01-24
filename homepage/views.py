from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ContactForm
from .models import ContactMessage
from django.contrib.auth.decorators import user_passes_test
from .models import HistChessMagazine

def historical_chess_mags(request):
    # Nur aktive Magazine holen
    populate_historical_magazines()
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

from .models import HistChessMagazine

def populate_historical_magazines():
    # 1. Alle vorhandenen Einträge löschen, um Dubletten zu vermeiden
    HistChessMagazine.objects.all().delete()

    # 2. Liste der Magazine definieren
    magazines = [
        # --- German Language Magazines ---
        {
            "name": "(Neue) Wiener Schachzeitung",
            "link": "https://anno.onb.ac.at/cgi-content/anno-plus?aid=sze",
            "language": "German"
        },
        {
            "name": "Deutsche Schachzeitung (1846-1874)",
            "link": "https://anno.onb.ac.at/cgi-content/anno-plus?aid=szb",
            "language": "German"
        },
        {
            "name": "Deutsche Schachzeitung (1872-1895)",
            "link": "https://books.google.com/books?uid=109234184683057393226&as_coll=1001&source=gbs_lp_bookshelf_list",
            "language": "German"
        },
        {
            "name": "Berliner Schachzeitung (1897)",
            "link": "https://books.google.de/books?id=bV8FAAAAYAAJ&pg=PA1&dq=editions:0yR9v4WpLjoC&hl=de",
            "language": "German"
        },
        {
            "name": "Arbeiter Schachzeitung",
            "link": "https://anno.onb.ac.at/cgi-content/anno-plus?aid=asz",
            "language": "German"
        },
        {
            "name": "Österreichische Schachrundschau",
            "link": "https://anno.onb.ac.at/cgi-content/anno-plus?aid=srs",
            "language": "German"
        },
        {
            "name": "Akademisches Monatsheft für Schach",
            "link": "https://anno.onb.ac.at/cgi-content/anno-plus?aid=ams",
            "language": "German"
        },
        {
            "name": "Deutsches Wochenschach (1897)",
            "link": "https://books.google.de/books?id=EWEFAAAAYAAJ&pg=PA260&dq=editions:0yR9v4WpLjoC&hl=de",
            "language": "German"
        },
        {
            "name": "Schweizerische Schachzeitung (from 2000 on)",
            "link": "https://www.e-periodica.ch/digbib/volumes?UID=ssz-001",
            "language": "German"
        },

        # --- English Language Magazines ---
        {
            "name": "Chess monthly",
            "link": "https://babel.hathitrust.org/cgi/pt?id=njp.32101066133221",
            "language": "English"
        },
        {
            "name": "American Chess Bulletin (1904)",
            "link": "https://books.google.de/books?id=2yoCAAAAYAAJ&dq=American+Chess+Bulletin&source=gbs_navlinks_s",
            "language": "English"
        },
        {
            "name": "American Chess Magazine (1847)",
            "link": "https://books.google.de/books?id=f_QCAAAAYAAJ&dq=American+Chess+Magazine&source=gbs_navlinks_s",
            "language": "English"
        },
        {
            "name": "American Chess Magazine (Google Books Query)",
            "link": "https://www.google.de/search?tbm=bks&q=American+Chess+Magazine",
            "language": "English"
        },
        {
            "name": "The British Chess Magazine (1881)",
            "link": "https://www.google.de/books/edition/The_British_Chess_Magazine/aKZJAAAAYAAJ?hl=de&gbpv=1&dq=chess+magazine&printsec=frontcover",
            "language": "English"
        },
        {
            "name": "The British Chess Magazine (Google Books Query)",
            "link": "https://www.google.de/search?q=The+British+Chess+Magazine&hl=de&tbm=bks",
            "language": "English"
        },

        # --- Spanish Language Magazines ---
        {
            "name": "Revista internacional de ajedrez",
            "link": "https://hemerotecadigital.bne.es/hd/es/results?parent=198f9965-38ca-4e73-a2dc-2f49374e1ef2&t=alt-asc",
            "language": "Spanish"
        },
        {
            "name": "Revista Trebejos (1967-1974)",
            "link": "http://www.historiadelajedrezespanol.es/revistas/trebejos.htm",
            "language": "Spanish"
        },
        {
            "name": "Boletín de la Federación catalana de ajedrez (1964-1990)",
            "link": "http://www.historiadelajedrezespanol.es/revistas/fce.htm",
            "language": "Spanish"
        },
        {
            "name": "Revista El ajedrez (1979-1981)",
            "link": "http://www.historiadelajedrezespanol.es/revistas/el_ajedrez.htm",
            "language": "Spanish"
        },
        {
            "name": "Revista Mate Postal (1974-2009)",
            "link": "http://www.historiadelajedrezespanol.es/revistas/mate_postal.htm",
            "language": "Spanish"
        },

        # --- Other Language Magazines ---
        {
            "name": "Bulletin - Fédération française des échecs (1921-1924)",
            "link": "https://cplorg.contentdm.oclc.org/digital/collection/p4014coll20/id/48642/rec/6",
            "language": "Other"
        }
    ]

    # 3. Neue Einträge erstellen
    for mag_data in magazines:
        HistChessMagazine.objects.create(
            name=mag_data["name"],
            link=mag_data["link"],
            language=mag_data["language"],
            is_active=True
        )
