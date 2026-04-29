#!/bin/bash
# start_web.sh — Start the Dashboard Agent web interface.
# Usage: ./start_web.sh
# Config: server.conf  (HOST, PORT, LOG_DIR, LOG_LEVEL)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED="\033[31m"; GREEN="\033[32m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"

[ -d ".venv" ]          || { echo -e "${RED}[ERROR]${RESET} .venv not found. Run ./build.sh first."; exit 1; }
[ -f "../shared.conf" ] || { echo -e "${RED}[ERROR]${RESET} ../shared.conf not found."; exit 1; }
[ -f "server.conf" ]    || { echo -e "${RED}[ERROR]${RESET} server.conf not found."; exit 1; }

source ../shared.conf
source server.conf

[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo -e "${RED}[ERROR]${RESET} ANTHROPIC_API_KEY not set in shared.conf"; exit 1; }

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8888}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_LEVEL="${LOG_LEVEL:-info}"
LOG_FILE="$LOG_DIR/server.log"

mkdir -p "$LOG_DIR"

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║     Dashboard Agent — Web UI             ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo -e "  ${GREEN}Open:${RESET}    http://localhost:${PORT}"
echo -e "  ${CYAN}Logs:${RESET}    ${LOG_FILE}"
echo -e "  ${CYAN}Level:${RESET}   ${LOG_LEVEL}"
echo -e "  Press Ctrl+C to stop.\n"

.venv/bin/uvicorn server:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level "$LOG_LEVEL" \
    --access-log \
    --no-use-colors \
    2>&1 | awk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0; fflush() }' | tee -a "$LOG_FILE"
