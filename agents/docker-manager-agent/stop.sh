#!/bin/bash
# stop.sh — Stop the Docker Manager Agent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN="\033[32m"; YELLOW="\033[33m"; RESET="\033[0m"

if pkill -f "$SCRIPT_DIR/.venv" 2>/dev/null; then
    echo -e "${GREEN}[  OK  ]${RESET} Docker Manager Agent stopped."
else
    echo -e "${YELLOW}[ WARN ]${RESET} No running Docker Manager Agent found."
fi
