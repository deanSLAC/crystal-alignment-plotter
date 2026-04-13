#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=".streamlit.pid"
LOG_FILE=".streamlit.log"

if [[ -f "$PID_FILE" ]]; then
    existing_pid=$(cat "$PID_FILE")
    if kill -0 "$existing_pid" 2>/dev/null; then
        echo "Streamlit already running (PID $existing_pid)."
        echo "Use ./stop.sh first, or tail $LOG_FILE to inspect."
        exit 1
    fi
    rm -f "$PID_FILE"
fi

# shellcheck disable=SC1091
source venv/bin/activate

nohup streamlit run app.py \
    --server.address=127.0.0.1 \
    --server.port=8501 \
    --browser.serverAddress=localhost \
    --server.headless=true \
    > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

echo "Streamlit started (PID $(cat "$PID_FILE"))."
echo "  URL:  http://localhost:8501"
echo "  Log:  $LOG_FILE"
echo "  Stop: ./stop.sh"
