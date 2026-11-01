#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$ROOT_DIR/run"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

status_service() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "🟢 $name is RUNNING (PID: $pid)"
            return 0
        fi
    fi
    echo "⚪ $name is STOPPED"
    return 1
}

start_service() {
    local name="$1"
    local cmd="$2"
    local pid_file="$PID_DIR/$name.pid"
    local log_file="$LOG_DIR/$name.log"

    if status_service "$name" >/dev/null 2>&1; then
        echo "⚠️  $name is already running."
        return 0
    fi

    echo "🚀 Starting $name..."
    nohup bash -c "$cmd" > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        echo "✅ $name started successfully (PID: $pid, Log: logs/$name.log)"
    else
        echo "❌ $name failed to start. Check $log_file"
        return 1
    fi
}

stop_service() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        echo "🛑 Stopping $name (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        for _ in {1..10}; do
            if ! kill -0 "$pid" 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        rm -f "$pid_file"
        echo "✅ $name stopped."
    else
        echo "⚪ $name is not running."
    fi
}

case "${1:-status}" in
    start)
        echo "=== Starting AI Stock Arena Services ==="
        start_service "api" "bash $ROOT_DIR/scripts/linux/run-api.sh"
        start_service "dashboard" "bash $ROOT_DIR/scripts/linux/run-dashboard.sh"
        start_service "v2" "bash $ROOT_DIR/scripts/linux/run-v2.sh"
        start_service "scheduler" "bash $ROOT_DIR/scripts/linux/run-scheduler.sh"
        echo ""
        $0 status
        ;;
    stop)
        echo "=== Stopping AI Stock Arena Services ==="
        stop_service "scheduler"
        stop_service "v2"
        stop_service "dashboard"
        stop_service "api"
        # Also clean up any lingering processes on ports
        fuser -k 8000/tcp 2>/dev/null || true
        fuser -k 8501/tcp 2>/dev/null || true
        fuser -k 3001/tcp 2>/dev/null || true
        ;;
    restart)
        $0 stop
        sleep 1
        $0 start
        ;;
    status)
        echo "=== AI Stock Arena Service Status ==="
        status_service "api" || true
        status_service "dashboard" || true
        status_service "v2" || true
        status_service "scheduler" || true
        echo ""
        echo "Health Checks:"
        if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "  API (8000): 🟢 OK"
        else
            echo "  API (8000): 🔴 Down"
        fi
        if curl -sf http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
            echo "  Streamlit V1 (8501): 🟢 OK"
        else
            echo "  Streamlit V1 (8501): 🔴 Down"
        fi
        if curl -sf http://127.0.0.1:3001/ >/dev/null 2>&1; then
            echo "  React V2 (3001): 🟢 OK"
        else
            echo "  React V2 (3001): 🔴 Down"
        fi
        ;;
    switch-ui)
        target="${2:-status}"
        bash "$ROOT_DIR/scripts/linux/switch-frontend.sh" "$target"
        ;;
    logs)
        target="${2:-api}"
        tail -f "$LOG_DIR/$target.log"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|switch-ui [v1|v2]|logs [api|dashboard|v2|scheduler]}"
        exit 1
        ;;
esac
