#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${APP_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/src"
exec "$VENV_PYTHON" -m uvicorn app.api.main:app --app-dir src --host 127.0.0.1 --port 8000
