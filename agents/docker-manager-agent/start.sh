#!/bin/bash
# start.sh — Start the Docker Orchestrator Agent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED="\033[31m"; GREEN="\033[32m"; BOLD="\033[1m"; RESET="\033[0m"

[ -d ".venv" ]          || { echo -e "${RED}[ERROR]${RESET} .venv not found — run ./build.sh first."; exit 1; }
[ -f "../shared.conf" ] || { echo -e "${RED}[ERROR]${RESET} ../shared.conf not found."; exit 1; }
[ -f "server.conf" ]    || { echo -e "${RED}[ERROR]${RESET} server.conf not found."; exit 1; }

source ../shared.conf
source server.conf

[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo -e "${RED}[ERROR]${RESET} ANTHROPIC_API_KEY not set in shared.conf"; exit 1; }
export ANTHROPIC_API_KEY

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8889}"
LOG_LEVEL="${LOG_LEVEL:-info}"
LOG_FILE="$SCRIPT_DIR/docker_agent/memory/server.log"

mkdir -p docker_agent/memory

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Docker Manager Agent                   ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo -e "  ${GREEN}API:${RESET}  http://localhost:${PORT}"
echo -e "  ${GREEN}Docs:${RESET} http://localhost:${PORT}/docs"
echo -e "  ${GREEN}Log:${RESET}  ${LOG_FILE}"
echo -e "  Press Ctrl+C to stop.\n"

cd docker_agent
../.venv/bin/uvicorn server:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level "$LOG_LEVEL" \
    --access-log \
    --no-use-colors \
    2>&1 | awk '{ print strftime("[%Y-%m-%d %H:%M:%S]"), $0; fflush() }' | tee -a "$LOG_FILE"
