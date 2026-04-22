#!/bin/bash
set -euo pipefail

pid=$(pgrep -f "claude" 2>/dev/null || true)

if [ -z "$pid" ]; then
    echo "No running Claude process found."
    exit 0
fi

echo "Stopping Claude (PID $pid)..."
kill "$pid"
echo "Done."
