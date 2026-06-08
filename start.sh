#!/usr/bin/env bash
# VibeListen Launcher (Unix)
# Starts the FastAPI web server and background worker in parallel.
#
# Usage:
#     ./start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    . "$SCRIPT_DIR/.venv/bin/activate"
fi

# Set PYTHONPATH so backend imports resolve correctly
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
    echo "[Launcher] Stopping processes..."
    if [[ -n "${SERVER_PID:-}" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    if [[ -n "${WORKER_PID:-}" ]]; then
        kill "$WORKER_PID" 2>/dev/null || true
        wait "$WORKER_PID" 2>/dev/null || true
    fi
    echo "[Launcher] All processes stopped."
    exit 0
}

trap cleanup INT TERM

echo "[Launcher] Starting VibeListen server and worker..."
echo "[Launcher] Project root: $SCRIPT_DIR"

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

python backend/worker.py &
WORKER_PID=$!

echo "[Launcher] Both processes started (PIDs: server=$SERVER_PID, worker=$WORKER_PID)."
echo "[Launcher] Press Ctrl+C to stop."

# Wait for either process to exit
wait -n 2>/dev/null || true

# If we get here, one process died — clean up the other
cleanup
