#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/var/log/ai-stock-arena/watchdog.log"
API_HEALTH_URL="http://127.0.0.1:8000/health"
RANKINGS_URL="http://127.0.0.1:8000/rankings?selected_only=true"
DASHBOARD_URL="http://127.0.0.1:8501/_stcore/health"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_FILE"
}

check_url() {
  local url="$1"
  local timeout_seconds="${2:-20}"
  curl --silent --show-error --fail --max-time "$timeout_seconds" "$url" >/dev/null
}

if ! check_url "$API_HEALTH_URL" 20; then
  log "api health failed; restarting api service"
  systemctl restart ai-stock-arena-api.service
fi

if ! check_url "$RANKINGS_URL" 35; then
  log "rankings endpoint failed; leaving api running"
fi

if ! check_url "$DASHBOARD_URL" 25; then
  log "dashboard failed; restarting dashboard service"
  systemctl restart ai-stock-arena-dashboard.service
fi

available_kb="$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
if [ "${available_kb:-0}" -lt 102400 ]; then
  log "low memory: MemAvailable=${available_kb}kB"
fi

log "watchdog ok"
