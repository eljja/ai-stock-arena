#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/ai-stock-arena/current"
BRANCH="${1:-main}"

cd "$APP_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m app.cli.bootstrap --skip-openrouter-sync
sudo systemctl restart ai-stock-arena-api.service
sudo systemctl restart ai-stock-arena-dashboard.service
sudo systemctl restart ai-stock-arena-scheduler.service

echo "Deployment complete for branch $BRANCH"
