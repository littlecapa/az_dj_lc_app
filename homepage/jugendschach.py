"""Inhalte der Seiten /jugendschach/ und /jugendschach/training/ (Schachjugend SC Bonn Beuel).

Übergangslösung, solange die Vereins-Homepage (WordPress) nicht gepflegt werden kann.
Jede Reihe ist eine Gruppe von Kacheln. Kacheln mit `'url': None` erscheinen als „Link folgt“.
"""

DRIVE_FLYER = "https://drive.google.com/file/d/1KDYvq2kj127JzyGvHMhpnN3IZeJj7ACT/view?usp=sharing"
DRIVE_AUFNAHMEANTRAG = "https://drive.google.com/file/d/1CGJVcT7w2cBvCX3kPqpgOnWb1RuruRQM/view?usp=sharing"
DRIVE_LEITFADEN_MF = "https://drive.google.com/file/d/1gSEdgQMhUn1DR3beZbm5pognXjd4KecE/view?usp=sharing"

CLUB_HOMEPAGE = "https://scbb.de"
INSTAGRAM = "https://www.instagram.com/schachclub_bonn_beuel/"
JUGEND_MAIL = "sccb.jugendschach@gmail.com"

INTRO = (
    "Wir haben Spaß daran, gegeneinander zu spielen – und können dabei auch mit „älteren“ "
    "Gegnern locker mithalten. Erste Erfolge sprechen für uns!"
)

# Kontakt-Kachel im Kopf beider Seiten (rechts neben Logo und Überschrift)
CONTACT = [
    {'icon': '✉️', 'text': JUGEND_MAIL, 'url': f'mailto:{JUGEND_MAIL}'},
    {'icon': '🌐', 'text': 'scbb.de', 'url': CLUB_HOMEPAGE},
    {'icon': '📷', 'text': '@schachclub_bonn_beuel', 'url': INSTAGRAM},
]

# Detailseite /jugendschach/training/ – Inhalte laut Flyer
TRAINING_TILES = [
    {'icon': '🕔', 'title': 'Wann?',
     'lines': ['Jeden Dienstag, 17–19 Uhr', 'In den Ferien bitte vorher kurz nachfragen.']},
    {'icon': '📍', 'title': 'Wo?',
     'lines': ['Mehrzweckraum des Tenten – Haus der Begegnung', 'An der Wolfsburg 1, 53225 Bonn'],
     'url': 'https://www.google.com/maps/search/?api=1&query=An+der+Wolfsburg+1,+53225+Bonn',
     'link_text': 'Karte öffnen'},
    {'icon': '♟', 'title': 'So läuft’s ab',
     'lines': ['1. Stunde Training (Taktik, Endspiel)', 'danach Blitz- oder Schnellschachturnier']},
    {'icon': '👋', 'title': 'Einfach vorbeikommen!',
     'lines': ['Die ersten Trainings sind kostenlos, eine Anmeldung ist nicht erforderlich.',
               'Eltern sind herzlich willkommen.']},
    {'icon': '👕', 'title': 'Mitglied werden (freiwillig)',
     'lines': ['Jahresbeitrag für Jugendliche: 45 € – 2026 ist beitragsfrei!',
               'Jedes Mitglied bekommt ein cooles Vereins-T-Shirt gratis.']},
    {'icon': '📄', 'title': 'Flyer', 'lines': ['Alle Infos zum Jugendtraining zum Weitergeben (PDF).'],
     'url': DRIVE_FLYER, 'link_text': 'Flyer öffnen'},
]

# Übersichtsseite /jugendschach/: eine Kachel führt zur Trainings-Seite (URL setzt die View)
TRAINING_TEASER = {
    'icon': '♟', 'title': 'Jugendschachtraining',
    'lines': ['Jeden Dienstag, 17–19 Uhr, Haus der Begegnung in Beuel.',
              'Einfach vorbeikommen – die ersten Trainings sind kostenlos.'],
    'link_text': 'Alle Infos zum Training',
}

TEAMS = [
    {
        'label': '5. Mannschaft',
        'tiles': [
            {'icon': '🗳', 'title': 'Umfrage: Wer spielt mit?',
             'lines': ['Rallly-Umfrage zu den Spielterminen.'],
             'url': 'https://app.rallly.co/invite/XSaJuRWVX5LP', 'link_text': 'Zur Umfrage'},
            {'icon': '🏆', 'title': 'Ergebnisse & Tabelle',
             'lines': ['Rangliste im Ergebnisportal des Schachverbands Mittelrhein.'],
             'url': ('https://ergebnisportal.sv-mittelrhein.de/index.php/component/clm/'
                     '?view=rangliste&saison=6&liga=145&Itemid=101&typeid=21'),
             'link_text': 'Zur Tabelle'},
        ],
    },
    {
        'label': 'U16-Mannschaft',
        'tiles': [
            {'icon': '🗳', 'title': 'Umfrage: Wer spielt mit?',
             'lines': ['Rallly-Umfrage zu den Spielterminen.'],
             'url': 'https://app.rallly.co/invite/qdTc685PcMgf', 'link_text': 'Zur Umfrage'},
            {'icon': '🏆', 'title': 'Ergebnisse & Tabelle',
             'lines': ['Rangliste bei der Schachjugend Mittelrhein.'],
             'url': ('https://www.schachjugend-mittelrhein.de/index.php/component/clm/'
                     '?view=rangliste&saison=26&liga=196&Itemid=1&typeid=21'),
             'link_text': 'Zur Tabelle'},
        ],
    },
]

CLUB_TILES = [
    {'icon': '📝', 'title': 'Aufnahmeantrag', 'lines': ['Formular für den Vereinseintritt (PDF).'],
     'url': DRIVE_AUFNAHMEANTRAG, 'link_text': 'Antrag öffnen'},
    {'icon': '📋', 'title': 'Infos für Mannschaftsführer',
     'lines': ['Richtlinien für die Mannschaftsführer, Saison 2026/27 (PDF).'],
     'url': DRIVE_LEITFADEN_MF, 'link_text': 'Leitfaden öffnen'},
]


def header_context():
    return {'intro': INTRO, 'contact': CONTACT}


NAECHSTE_TERMINE_ANZAHL = 2


def naechste_termine(anzahl=NAECHSTE_TERMINE_ANZAHL):
    """Die nächsten aktiven Termine ab heute (Datum in deutscher Ortszeit), Pflege im Admin (JugendTermin)."""
    from zoneinfo import ZoneInfo
    from django.utils import timezone
    from .models import JugendTermin
    heute = timezone.localdate(timezone=ZoneInfo('Europe/Berlin'))
    return list(JugendTermin.objects.filter(is_active=True, datum__gte=heute)[:anzahl])
