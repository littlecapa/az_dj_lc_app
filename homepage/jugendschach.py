"""Inhalte der Seite /jugendschach/ (Schachjugend SC Bonn Beuel).

Übergangslösung, solange die Vereins-Homepage (WordPress) nicht gepflegt werden kann.
Jede Reihe ist eine Gruppe von Kacheln. Kacheln ohne `url` erscheinen als „Link folgt“.
"""

DRIVE_FLYER = "https://drive.google.com/file/d/1KDYvq2kj127JzyGvHMhpnN3IZeJj7ACT/view?usp=sharing"
DRIVE_AUFNAHMEANTRAG = "https://drive.google.com/file/d/1CGJVcT7w2cBvCX3kPqpgOnWb1RuruRQM/view?usp=sharing"
DRIVE_LEITFADEN_MF = "https://drive.google.com/file/d/1gSEdgQMhUn1DR3beZbm5pognXjd4KecE/view?usp=sharing"

CLUB_HOMEPAGE = "https://scbb.de"
INSTAGRAM = "https://www.instagram.com/schachclub_bonn_beuel/"
JUGEND_MAIL = "sccb.jugendschach@gmail.com"

# Jugendtraining laut Flyer
TRAINING = {
    'intro': (
        "Wir haben Spaß daran, gegeneinander zu spielen – und können dabei auch mit „älteren“ "
        "Gegnern locker mithalten. Erste Erfolge sprechen für uns!"
    ),
    'tiles': [
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
        {'icon': '✉️', 'title': 'Kontakt',
         'lines': [JUGEND_MAIL, 'Instagram: @schachclub_bonn_beuel'],
         'url': f'mailto:{JUGEND_MAIL}', 'link_text': 'E-Mail schreiben'},
    ],
}

TEAMS = [
    {
        'label': '5. Mannschaft',
        'tiles': [
            {'icon': '🗳', 'title': 'Umfrage: Wer spielt mit?',
             'lines': ['Rallly-Umfrage zu den Spielterminen.'], 'url': None},
            {'icon': '🏆', 'title': 'Ergebnisse & Tabelle',
             'lines': ['Mannschaftskämpfe im Schachbezirk Bonn/Rhein-Sieg.'], 'url': None},
        ],
    },
    {
        'label': 'U16-Mannschaft',
        'tiles': [
            {'icon': '🗳', 'title': 'Umfrage: Wer spielt mit?',
             'lines': ['Rallly-Umfrage zu den Spielterminen.'], 'url': None},
            {'icon': '🏆', 'title': 'Ergebnisse & Tabelle',
             'lines': ['Ergebnisse der U16-Mannschaft.'], 'url': None},
        ],
    },
]

CLUB_TILES = [
    {'icon': '🏰', 'title': 'Vereins-Homepage', 'lines': ['Alles rund um den SC Bonn Beuel.'],
     'url': CLUB_HOMEPAGE, 'link_text': 'scbb.de'},
    {'icon': '📝', 'title': 'Aufnahmeantrag', 'lines': ['Formular für den Vereinseintritt (PDF).'],
     'url': DRIVE_AUFNAHMEANTRAG, 'link_text': 'Antrag öffnen'},
    {'icon': '📋', 'title': 'Infos für Mannschaftsführer',
     'lines': ['Richtlinien für die Mannschaftsführer, Saison 2026/27 (PDF).'],
     'url': DRIVE_LEITFADEN_MF, 'link_text': 'Leitfaden öffnen'},
]


def context():
    return {
        'training': TRAINING,
        'teams': TEAMS,
        'club_tiles': CLUB_TILES,
        'flyer_url': DRIVE_FLYER,
        'instagram_url': INSTAGRAM,
    }
