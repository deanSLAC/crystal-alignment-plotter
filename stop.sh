#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=".streamlit.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No PID file ($PID_FILE). Nothing to stop."
    exit 0
fi

pid=$(cat "$PID_FILE")

if ! kill -0 "$pid" 2>/dev/null; then
    echo "PID $pid not running. Removing stale PID file."
    rm -f "$PID_FILE"
    exit 0
fi

echo "Stopping streamlit (PID $pid)..."
kill "$pid"

# Wait up to 5s for graceful shutdown
for _ in {1..10}; do
    if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "Stopped."
        exit 0
    fi
    sleep 0.5
done

echo "Did not exit in 5s; sending SIGKILL."
kill -9 "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
echo "Killed."
