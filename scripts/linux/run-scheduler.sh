#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/opt/ai-stock-arena/current"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/src"
exec "$VENV_PYTHON" -m app.cli.scheduler serve
