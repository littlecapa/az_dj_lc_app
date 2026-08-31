#!/usr/bin/env zsh
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

python3 scripts/scalable_mcp_local_login.py "$@"
