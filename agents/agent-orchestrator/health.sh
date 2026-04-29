#!/bin/bash
# health.sh — Check dashboard agent is ready to run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"

pass() { echo -e "${GREEN}[  OK  ]${RESET} $*"; }
fail() { echo -e "${RED}[ FAIL ]${RESET} $*"; OVERALL=1; }
warn() { echo -e "${YELLOW}[ WARN ]${RESET} $*"; }
info() { echo -e "         ${DIM}$*${RESET}"; }

OVERALL=0

echo -e "\n${BOLD}Dashboard Agent — Health Check${RESET}\n"

command -v python3 &>/dev/null \
    && pass "Python $(python3 --version 2>&1 | awk '{print $2}')" \
    || fail "python3 not found"

[ -d ".venv" ] && pass ".venv exists" || fail ".venv missing — run ./build.sh"

if [ -d ".venv" ]; then
    MISSING=""
    for pkg in anthropic dotenv fastapi uvicorn; do
        .venv/bin/python -c "import $pkg" 2>/dev/null || MISSING="$MISSING $pkg"
    done
    [ -z "$MISSING" ] && pass "Dependencies installed" || fail "Missing:$MISSING — run ./build.sh"
fi

if [ -f "../shared.conf" ]; then
    pass "shared.conf exists"
    source ../shared.conf 2>/dev/null || true
    [ -n "${ANTHROPIC_API_KEY:-}" ] \
        && pass "ANTHROPIC_API_KEY set (${ANTHROPIC_API_KEY:0:10}...)" \
        || fail "ANTHROPIC_API_KEY not set"
else
    fail "shared.conf not found at agents/shared.conf"
fi

if [ -d "static" ] && [ -f "static/index.html" ]; then
    pass "static/ assets present"
else
    fail "static/index.html missing"
fi

[ -f "server.conf" ] && pass "server.conf exists" || fail "server.conf not found"

source server.conf 2>/dev/null || true
PORT="${PORT:-8888}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="$LOG_DIR/server.log"

if ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
    pass "Dashboard agent is running (port ${PORT})"
else
    warn "Dashboard agent is not running — run ./start_web.sh"
fi

if [ -f "$LOG_FILE" ]; then
    LINES=$(wc -l < "$LOG_FILE")
    pass "Log file: $LOG_FILE ($LINES lines)"
else
    warn "Log file not found: $LOG_FILE"
fi

echo ""
echo "──────────────────────────────────────────"
if [ "$OVERALL" -eq 0 ]; then
    echo -e "Status: ${GREEN}HEALTHY${RESET} — run ./start_web.sh to begin"
else
    echo -e "Status: ${RED}UNHEALTHY${RESET} — fix the issues above"
fi
echo ""
exit $OVERALL
