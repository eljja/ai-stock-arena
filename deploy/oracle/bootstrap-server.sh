#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/ai-stock-arena"
APP_DIR="$APP_ROOT/current"
REPO_URL="${1:-https://github.com/eljja/ai-stock-arena.git}"
BRANCH="${2:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ENV_FILE="/etc/ai-stock-arena/ai-stock-arena.env"

sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip nginx

sudo mkdir -p "$APP_ROOT" /etc/ai-stock-arena /var/log/ai-stock-arena
sudo chown -R "$USER":"$USER" "$APP_ROOT"

if [ ! -d "$APP_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
fi

cd "$APP_DIR"
$PYTHON_BIN -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

chmod +x scripts/linux/run-api.sh scripts/linux/run-dashboard.sh scripts/linux/run-scheduler.sh

if [ ! -f "$ENV_FILE" ]; then
  sudo cp .env.example "$ENV_FILE"
  sudo chown root:root "$ENV_FILE"
  sudo chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example. Fill in secrets before starting services."
fi

echo "Oracle bootstrap complete. Next steps:"
echo "1. Edit $ENV_FILE"
echo "2. Copy deploy/oracle/systemd/*.service into /etc/systemd/system/"
echo "3. Copy deploy/oracle/nginx/ai-stock-arena.conf into /etc/nginx/sites-available/"
echo "4. Enable nginx and systemd services"
