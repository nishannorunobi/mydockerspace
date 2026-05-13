#!/bin/bash
# start.sh — Start claude-code-proxy on the host (port 8892).
# Docker containers call it via http://host.docker.internal:8892
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN="\033[32m"; CYAN="\033[36m"; RED="\033[31m"; BOLD="\033[1m"; RESET="\033[0m"

PORT="${PORT:-8892}"
LOG="$SCRIPT_DIR/proxy.log"

# Resolve claude binary — check PATH and common NVM locations
if command -v claude &>/dev/null; then
    CLAUDE_BIN="$(command -v claude)"
elif [ -f "$HOME/.nvm/versions/node/v24.13.0/bin/claude" ]; then
    CLAUDE_BIN="$HOME/.nvm/versions/node/v24.13.0/bin/claude"
else
    CLAUDE_BIN="${CLAUDE_BIN:-claude}"
fi

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Claude Code Proxy                      ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo -e "  ${GREEN}Port:${RESET}   $PORT"
echo -e "  ${GREEN}Claude:${RESET} $CLAUDE_BIN"
echo -e "  ${GREEN}Log:${RESET}    $LOG\n"

if ! command -v "$CLAUDE_BIN" &>/dev/null && [ ! -f "$CLAUDE_BIN" ]; then
    echo -e "${RED}[ERROR]${RESET} claude not found. Install Claude Code first."
    exit 1
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo -e "${CYAN}[INFO]${RESET}  Creating venv..."
    python3 -m venv .venv
    .venv/bin/pip install --quiet fastapi "uvicorn[standard]" pydantic
    echo -e "${GREEN}[ OK ]${RESET}  venv ready."
fi

export PORT CLAUDE_BIN

exec .venv/bin/uvicorn server:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level info \
    2>&1 | awk '{ print strftime("[%H:%M:%S]"), $0; fflush() }' | tee -a "$LOG"
