"""Bereiche der Website für die Übersicht /menue. Neue Bereiche hier eintragen.

access: public (alle), login (eingeloggt), staff (Admin-Login), superuser.
"""

ACCESS_CHECKS = {
    'public': lambda user: True,
    'login': lambda user: user.is_authenticated,
    'staff': lambda user: user.is_staff,
    'superuser': lambda user: user.is_superuser,
}

SECTIONS = [
    ('💶 Finanzen', [
        # immer sichtbar: ohne Login führt /fintech/ zur Anmeldung
        ('fintech:fintech-index', '📈', 'Fintech', 'Portfolio, Watchlisten, News, Alarme und Verwaltung (Login nötig).',
         'public'),
        ('fintech_demo:fintech-index', '🎭', 'Fintech-Demo', 'Der Fintech-Bereich mit Beispieldaten.', 'public'),
    ]),
    ('🎶 Freizeit', [
        ('leisure:index', '🎤', 'Leisure', 'Konzerte, Artists und Venues: Vorschläge prüfen und abstimmen.', 'public'),
        ('leisure:event-voting', '🗳', 'Konzert-Abstimmung', 'Freunde stimmen ab, zu welchen Konzerten sie mitkommen.', 'public'),
        ('bordkasse:index', '⛵', 'Bordkasse', 'Gemeinsame Kasse und Einkaufsliste für Segeltörns.', 'public'),
        ('travel:index', '✈️', 'Reisen', 'Flug- und Routensuche.', 'public'),
        ('recipes:index', '🍝', 'Rezepte', 'Rezeptsammlung mit Import.', 'public'),
    ]),
    ('♟ Schach', [
        ('chess:index', '♟', 'Chess', 'Schach-Seite.', 'public'),
        ('homepage:my_chess_club', '🏰', 'My Chess Club', 'Mein Schachverein.', 'public'),
        ('homepage:historical-chess-mags', '📚', 'Historical Chess Mags', 'Historische Schachzeitschriften.', 'public'),
        ('homepage:scbb', '📡', 'SCBB-Monitor', 'Überwachung der SCBB-Seite.', 'public'),
    ]),
    ('🙋 Persönlich', [
        ('bp_list', '❤️', 'Blutdruck', 'Messwerte mit CSV-Export.', 'login'),
        ('telegram_app:send_message', '✉️', 'Telegram', 'Nachricht per Telegram senden.', 'login'),
    ]),
    ('⚙️ System', [
        ('tasks:list', '⏱', 'Tasks', 'Alle automatischen Läufe und ihr letzter Status.', 'staff'),
        ('core:mcp_index', '🔌', 'MCP-Verbindungen', 'Externe MCP-Provider verbinden.', 'login'),
        ('core:jira', '🧩', 'Jira', 'Jira-Tickets.', 'login'),
        ('homepage:api-overview', '🧭', 'API-Übersicht', 'Alle API-Endpunkte.', 'login'),
        ('homepage:monitoring', '🩺', 'Monitoring', 'Systemzustand.', 'superuser'),
        ('homepage:dashboard', '📊', 'Zugriffsstatistik', 'Aufrufe der letzten 30 Tage.', 'superuser'),
        ('admin:index', '🛠', 'Admin', 'Django-Admin für alle Daten.', 'staff'),
    ]),
    ('🌐 Website', [
        ('homepage:blog', '📝', 'Blog', 'Meine Beiträge.', 'public'),
        ('homepage:links', '🔗', 'Links', 'Linksammlung.', 'public'),
        ('homepage:contact', '📮', 'Kontakt', 'Kontaktformular.', 'public'),
    ]),
]


def visible_sections(user):
    """Die Abschnitte mit den Einträgen, die der Benutzer öffnen darf; leere Abschnitte fallen weg."""
    result = []
    for title, entries in SECTIONS:
        items = [{'url_name': url_name, 'icon': icon, 'title': name, 'desc': desc}
                 for url_name, icon, name, desc, access in entries if ACCESS_CHECKS[access](user)]
        if items:
            result.append({'title': title, 'items': items})
    return result
