#!/usr/bin/env zsh
set -e

WORKFLOW="update_prices.yml"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$REPO_DIR"

if ! gh auth status &>/dev/null; then
  echo "Bitte einmalig bei GitHub einloggen:"
  gh auth login
fi

gh workflow run "$WORKFLOW" --ref main
echo "Workflow gestartet. Status: https://github.com/littlecapa/az_dj_lc_app/actions"

# Nebenbei: SCBB-Erreichbarkeits-Check anstoßen (nutzt den bestehenden Cron-Takt).
# Darf den Preis-Update-Trigger nicht blockieren, falls scbb.de/die App nicht erreichbar ist.
if curl -s -o /dev/null -w '%{http_code}' -X POST --max-time 40 https://littlecapa.com/scbb/check/ | grep -q '^2'; then
  echo "SCBB-Check ausgelöst."
else
  echo "SCBB-Check fehlgeschlagen (ignoriert)."
fi
