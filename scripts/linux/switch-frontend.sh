#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-status}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_DIR="${PROJECT_ROOT}/deploy"

if [ "$TARGET" = "v1" ]; then
  echo "Switching main frontend to V1 (Streamlit on port 8501)..."
  curl -s -X POST http://localhost:2019/load -H "Content-Type: text/caddyfile" --data-binary @"${DEPLOY_DIR}/Caddyfile.v1"
  cp -f "${DEPLOY_DIR}/Caddyfile.v1" "${DEPLOY_DIR}/Caddyfile"
  echo "Successfully switched to V1! https://aistockarena.com/ is now Streamlit."
elif [ "$TARGET" = "v2" ]; then
  echo "Switching main frontend to V2 (React SPA on port 3001)..."
  curl -s -X POST http://localhost:2019/load -H "Content-Type: text/caddyfile" --data-binary @"${DEPLOY_DIR}/Caddyfile.v2"
  cp -f "${DEPLOY_DIR}/Caddyfile.v2" "${DEPLOY_DIR}/Caddyfile"
  echo "Successfully switched to V2! https://aistockarena.com/ is now React SPA."
elif [ "$TARGET" = "status" ]; then
  echo "=== Current active frontend status ==="
  curl -s -I --resolve aistockarena.com:443:127.0.0.1 https://aistockarena.com/ | grep -iE "HTTP|server|content-type"
else
  echo "Usage: $0 [v1|v2|status]"
  echo "  v1: Rollback main dashboard to Streamlit"
  echo "  v2: Set main dashboard to React V2"
  echo "  status: Show current active dashboard"
  exit 1
fi
