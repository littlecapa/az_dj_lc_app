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
