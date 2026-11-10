# az_dj_lc_app — Claude-Hinweise

## Git-Workflow
- **Commits bündeln**: Zusammengehörige Änderungen (Model + Migration + View + Admin) immer in einem einzigen Commit zusammenfassen — niemals einzeln pushen.
- Grund: Jeder Push triggert den Azure-Deploy-Workflow. Zwei schnelle Pushes führen zu einem 409-Konflikt auf Azure.

## Azure-Deployment
- Deploy läuft via GitHub Actions (`.github/workflows/main_lc-app-live.yml`) bei jedem Push auf `main`.
- Manuelles Neu-Starten eines fehlgeschlagenen Runs: `gh run rerun <run-id>`
- Preisupdate manuell triggern: `./trigger_price_update.sh`
- ETF-Holdings-Update manuell triggern: `./trigger_etf_holdings.sh`
- News-Update manuell triggern: `./trigger_update_news.sh`

## Django-Struktur
- Hauptapp: `fintech/`
- Portfolio-Export-View: `GET /fintech/export` — Auth via API-Key (`X-Api-Key`) oder Staff-Login
- Kurs-Update: `python manage.py update_prices [--asset-class CLASS] [--isin ISIN] [--dry-run]`
- ETF-Holdings-Update: `python manage.py update_etf_holdings [--isin ISIN] [--dry-run]` — holt Top-10-Holdings
  aller gehaltenen ETFs/Fonds via JustETF, pflegt `FondHolding`-Mapping. Legt für Aktien ohne eigene
  Holdings-Zeile einen Dummy-Eintrag (quantity=0) an, damit sie im Aktien-Look-Through
  (`/fintech/overall-stocks/`) mit aktuellem Kurs erscheinen. `Holdings.quantity == 0` ist seitdem ein
  gültiger Dauerzustand (kein Bug) — wird in allen normalen Portfolio-Listen ausgeblendet.
- News-Update: `python manage.py update_news [--min-value 3000] [--dry-run]` — holt News (Yahoo Finance +
  Google News RSS) für Aktien mit Look-Through-Wert (siehe `/fintech/overall-stocks/`) über der Schwelle,
  speichert sie dedupliziert in `NewsArticle`. Feed-Seite: `/fintech/news-feed/` (liest nur die DB, ruft
  nichts live ab).
- ISIN-Wechsel: `python manage.py change_isin ALT NEU [--dry-run] [--skip-attributes]` bzw. Seite
  `/fintech/isin-change/` (Kachel „ISIN-Wechsel“) — zieht ein Asset auf eine neue ISIN um (ISIN ist der PK):
  Kopie anlegen, alle FKs auf Asset generisch umhängen, altes Asset löschen, danach WKN/Symbol/Yahoo-Symbol/Kurs
  neu ermitteln. Logik in `fintech/isin_change.py`; der Dry-Run führt alles aus und rollt zurück.
- Bordkasse: `/bordkasse/` (Törn-Liste) und `/bordkasse/<slug>/` (Kasse, Einkaufsliste, Historie). Neuer Törn
  nur eingeloggt; alles andere frei, solange `Bordkasse_Konfig.Authentifizierung_erforderlich` False ist (Default).
  Daten per JSON-API unter
  `/bordkasse/<slug>/api/…`, Excel-Export `/bordkasse/<slug>/export.xlsx`. Buchungen referenzieren Crew per FK
  (Umbenennen wirkt überall), Löschen ist Soft-Delete, Bearbeitungen landen als `BuchungRevision`.
  Standard-Einkaufsliste in den Tabellen `StandardKategorie`/`StandardArtikel` (Pflege im Admin, Startbestand per Migration 0003).
  `Bordkasse_Konfig.Authentifizierung_erforderlich` (Admin) = True → alle Bordkassen-Seiten und API nur nach Login.
- MCP-Server (nur lesend): `POST /fintech/mcp` (`fintech/apis/mcp_server.py`) und `POST /leisure/mcp`
  (`leisure/mcp_server.py`; alte URL `/events/mcp` ist ein Übergangs-Alias), gemeinsamer Kern `core/mcp_server.py` (`ReadOnlyMcpView`), zustandsloses Streamable HTTP,
  Tools rufen intern die bestehenden lesenden API-Views auf. Auth nur per `Authorization: Bearer <MCP_READONLY_API_KEY>`
  — `FINTECH_API_KEY` und Admin-Session gelten dort bewusst nicht, der MCP-Key öffnet umgekehrt keine anderen Endpunkte.
  Neue Tools auf diesen Servern nur lesend (`get_…`, `readOnlyHint`), sonst schlägt `McpServerTests` bzw. `LeisureMcpTests` fehl.
  Einzige Schreib-Ausnahme: `POST /leisure/mcp/write` (`WriteMcpView`, nur `MCP_WRITE_API_KEY`, der Lese-Key gilt dort nicht
  und umgekehrt) mit `add_suggestions` (kind artist/venue/event, nur in `Suggestion`, nie direkt in die Listen) und `log_task_run`.
- Leisure (früher Events): `Venue` (früher Location), `Artist`, `UpcomingEvent`, Pflege im Admin unter „Leisure“. Die App
  `events` ist nur noch eine leere Hülle für die Migrationshistorie (Daten per `leisure.0002` übernommen) — keine neuen
  Modelle dort. Neue Konzerte schlägt die Cloud-Routine per `add_suggestions` vor (siehe unten); der JSON-Import
  bleibt für manuelle Funde (Format: Tool `get_import_format`,
  `leisure/importer.py`, Schlüssel `venues`/`artists`/`events`; alte Schlüssel `locations`/`location` werden noch angenommen);
  Import manuell im Admin (Upcoming Events → „JSON importieren“) oder `python manage.py import_events <datei> [--dry-run]`.
  Bestehende Venues/Artists werden nur ergänzt (Rating bleibt), Events nicht doppelt angelegt, bei Fehlern wird nichts gespeichert.
  Vorschläge: Claude legt per `add_suggestions` `Suggestion`s an (max. 5; Artists mit `Category` aus fester Liste, Pflege
  im Admin; Venues mit Land; Land und Links im `payload`); Logik in `leisure/suggestions.py` (`KINDS`). Bewertet wird unter
  `/leisure/new_artists`, `/leisure/new_venues` bzw. `/leisure/new_events` (nur Staff, gemeinsames Template
  `new_suggestions.html`): 👍 + Rating → Artist/Venue, 👎 → `rejected` = Blacklist, sonst bleibt offen.
  Konzerte (kind event, max. 30 pro Aufruf, Name „Artist @ Venue, YYYY-MM-DD“, Daten im `payload`): nur bekannte
  Artists; an einer fremden Venue nur Artists mit Rating ≥ 7 (`TOP_ARTIST_RATING`), die Venue wird dann zusätzlich
  als Venue-Vorschlag angelegt und muss vor dem Konzert übernommen werden. 👍 ohne Rating → `UpcomingEvent`,
  👎 = verworfen (wird nicht erneut angenommen).
  Abstimmung mit Freunden: `/leisure/new_events/voting` ist bewusst **öffentlich** (ohne Login, wie Doodle) und zeigt
  offene und übernommene Konzert-Vorschläge ab heute. `EventVote` (je Konzert-`Suggestion` eine Stimme pro Name,
  Name ohne Groß-/Kleinschreibung, 👍/😐/👎 + Kommentar); der Name steht in der Session, nicht in der URL.
  Die Summen erscheinen auf `/leisure/new_events`, alle Stimmen im Admin.
  `get_suggestions` liefert alle Status, damit Abgelehntes und Offenes nicht erneut vorgeschlagen wird.
- Tasks: zentrale Registry in der App `tasks` (`Task`: Name, Prompt, `executor` server/cowork/cloud, Sub-Tasks über
  `parent` + `position`, `interval_hours` für den Health-Check, `parameters` als JSON; `TaskRun` = Log je Lauf). Pflege im Admin.
  MCP `get_tasks`/`get_task` (`tasks/mcp_tools.py`, eingehängt in `/leisure/mcp`) — Cowork Scheduled Tasks holen ihren
  Prompt darüber, Prompt-Änderungen also im Admin, nicht in Cowork. Inaktive Tasks liefert der MCP-Server nicht aus.
  Server-Tasks (`executor=server`, `command` = Management-Command): Commands mit `TrackedCommandMixin`
  (`tasks/runner.py`; aktuell update_prices, update_news, update_etf_holdings) schreiben bei jedem regulären Lauf einen
  `TaskRun` — Dry-Run/Teilläufe (`untracked_options`) nicht; hängende Läufe > 30 Min gelten als Timeout.
  Claude-Tasks (cowork/cloud) melden ihre Läufe selbst per MCP `log_task_run`.
  Übersicht `/tasks/` (nur Staff): rot = letzter Lauf fehlgeschlagen oder überfällig (Intervall + 25 %, nur `run_days`).
- Übersicht: `/menue/` listet alle Bereiche als Kacheln (`homepage/menu.py`, `SECTIONS` mit Zugriffsstufe
  public/login/staff/superuser — gezeigt wird nur, was der Benutzer öffnen darf). Neue Bereiche dort eintragen.
  Kachel-Stil gemeinsam in `homepage/_tiles_style.html` (Fintech, Leisure, Menü). `/leisure/` ist die
  Leisure-Kachelseite: öffentlich nur die Abstimmung, der Rest nur für Staff.
- Fintech-Zugriff: alle Seiten/APIs unter `/fintech/` nur mit Admin-Login (`is_staff`) oder `X-Api-Key`;
  einzige Ausnahme ist der Demo-Bereich `/demo/fintech/`. `fintech/tests.py` prüft das für jede URL automatisch.
