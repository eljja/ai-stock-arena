#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/ai-stock-arena/current"
ENV_FILE="/etc/ai-stock-arena/ai-stock-arena.env"
CANDIDATE_LIMIT="${1:-250}"
SORT_BY="${2:-popular}"

cd "$APP_DIR"
set -a
source "$ENV_FILE"
set +a
export PYTHONPATH=src
./.venv/bin/python -m app.cli.models sync-free-models --candidate-limit "$CANDIDATE_LIMIT" --sort-by "$SORT_BY"
