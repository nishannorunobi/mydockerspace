#!/bin/bash
# start_daemon.sh — Start the workspace agent as a background daemon.
# The monitor runs silently; interact with the agent via the dashboard chat.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED="\033[31m"; GREEN="\033[32m"; RESET="\033[0m"

[ -d ".venv" ]          || { echo -e "${RED}[ERROR]${RESET} .venv not found. Run ./build.sh first."; exit 1; }
[ -f "../shared.conf" ] || { echo -e "${RED}[ERROR]${RESET} ../shared.conf not found."; exit 1; }

source ../shared.conf
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo -e "${RED}[ERROR]${RESET} ANTHROPIC_API_KEY not set in shared.conf"; exit 1; }
export ANTHROPIC_API_KEY

if pgrep -f "workspace/agent.py --daemon" &>/dev/null; then
    echo -e "${RED}[ERROR]${RESET} Workspace agent is already running (PID $(pgrep -f "workspace/agent.py --daemon" | head -1))."
    exit 1
fi

LOG_FILE="$SCRIPT_DIR/workspace/memory/daemon.log"

nohup "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/workspace/agent.py" --daemon \
    >> "$LOG_FILE" 2>&1 &

PID=$!
echo -e "${GREEN}[  OK  ]${RESET} Workspace agent daemon started (PID $PID)"
echo -e "         Log: $LOG_FILE"
