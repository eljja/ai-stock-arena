#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/ai-stock-arena/current"
ENV_FILE="/etc/ai-stock-arena/ai-stock-arena.env"
ADDITIONAL_COUNT="${1:-10}"
CANDIDATE_LIMIT="${2:-40}"
SORT_BY="${3:-popular}"

sudo bash -lc "
  set -a
  source '$ENV_FILE'
  set +a
  cd '$APP_DIR'
  export PYTHONPATH=src
  ./.venv/bin/python -m app.cli.models add-free-models --additional-count '$ADDITIONAL_COUNT' --candidate-limit '$CANDIDATE_LIMIT' --sort-by '$SORT_BY'
"
