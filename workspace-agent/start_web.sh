#!/bin/bash
# start_web.sh — Start the Workspace Agent web interface.
# Usage: ./start_web.sh [port]   (default port: 8888)
# Open: http://localhost:8888
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED="\033[31m"; GREEN="\033[32m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"

[ -d ".venv" ]      || { echo -e "${RED}[ERROR]${RESET} .venv not found. Run ./build.sh first."; exit 1; }
[ -f "agent.conf" ] || { echo -e "${RED}[ERROR]${RESET} agent.conf not found. Run ./build.sh first."; exit 1; }

source agent.conf
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo -e "${RED}[ERROR]${RESET} ANTHROPIC_API_KEY not set in agent.conf"; exit 1; }

PORT="${1:-8888}"

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║     Workspace Agent — Web UI             ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo -e "  ${GREEN}Open:${RESET}    http://localhost:${PORT}"
echo -e "  ${CYAN}Monitor:${RESET} watching workspace every 15s"
echo -e "  Press Ctrl+C to stop.\n"

.venv/bin/uvicorn server:app --host 0.0.0.0 --port "$PORT"
