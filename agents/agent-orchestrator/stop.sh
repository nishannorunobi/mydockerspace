#!/bin/bash
# stop.sh — Stop the running dashboard agent (uvicorn) process.
set -euo pipefail

GREEN="\033[32m"; YELLOW="\033[33m"; RESET="\033[0m"

PID=$(ss -tlnp 2>/dev/null | grep ':8888' | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$PID" ]; then
    kill "$PID" 2>/dev/null && echo -e "${GREEN}[ OK ]${RESET}  Dashboard agent stopped (PID $PID)."
else
    echo -e "${YELLOW}[WARN]${RESET}  No running dashboard agent found on port 8888."
fi
