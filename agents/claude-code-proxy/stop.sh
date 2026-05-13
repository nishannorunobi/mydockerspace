#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN="\033[32m"; RESET="\033[0m"

pkill -f "$SCRIPT_DIR/.venv" 2>/dev/null && echo -e "${GREEN}[ OK ]${RESET}  claude-code-proxy stopped." || echo "Not running."
