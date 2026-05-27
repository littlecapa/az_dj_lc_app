# az_dj_lc_app — Claude-Hinweise

## Git-Workflow
- **Commits bündeln**: Zusammengehörige Änderungen (Model + Migration + View + Admin) immer in einem einzigen Commit zusammenfassen — niemals einzeln pushen.
- Grund: Jeder Push triggert den Azure-Deploy-Workflow. Zwei schnelle Pushes führen zu einem 409-Konflikt auf Azure.

## Azure-Deployment
- Deploy läuft via GitHub Actions (`.github/workflows/main_lc-app-live.yml`) bei jedem Push auf `main`.
- Manuelles Neu-Starten eines fehlgeschlagenen Runs: `gh run rerun <run-id>`
- Preisupdate manuell triggern: `./trigger_price_update.sh`

## Django-Struktur
- Hauptapp: `fintech/`
- Portfolio-Export-View: `GET /fintech/export` — Auth via API-Key (`X-Api-Key`) oder Staff-Login
- Kurs-Update: `python manage.py update_prices [--asset-class CLASS] [--isin ISIN] [--dry-run]`
