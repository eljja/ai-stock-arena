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
chmod +x scripts/linux/run-api.sh scripts/linux/run-dashboard.sh scripts/linux/run-scheduler.sh scripts/linux/add-free-models.sh scripts/linux/sync-free-models.sh scripts/linux/watchdog.sh

sudo cp deploy/oracle/systemd/ai-stock-arena-api.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-dashboard.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-scheduler.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-watchdog.service /etc/systemd/system/
sudo cp deploy/oracle/systemd/ai-stock-arena-watchdog.timer /etc/systemd/system/
sudo cp deploy/oracle/logrotate/ai-stock-arena /etc/logrotate.d/ai-stock-arena
sudo systemctl daemon-reload
sudo systemctl enable ai-stock-arena-watchdog.timer
sudo systemctl start ai-stock-arena-watchdog.timer
sudo systemctl restart ai-stock-arena-api.service
sudo systemctl restart ai-stock-arena-dashboard.service
sudo systemctl restart ai-stock-arena-scheduler.service

echo "Deployment complete for branch $BRANCH"
