#!/usr/bin/env zsh
set -e

WORKFLOW="update_news.yml"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$REPO_DIR"

if ! gh auth status &>/dev/null; then
  echo "Bitte einmalig bei GitHub einloggen:"
  gh auth login
fi

gh workflow run "$WORKFLOW" --ref main
echo "Workflow gestartet. Status: https://github.com/littlecapa/az_dj_lc_app/actions"
