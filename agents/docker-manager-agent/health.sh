#!/bin/bash
# health.sh — Check docker-manager-agent health.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"
pass() { echo -e "${GREEN}[  OK  ]${RESET} $*"; }
fail() { echo -e "${RED}[ FAIL ]${RESET} $*"; OVERALL=1; }
warn() { echo -e "${YELLOW}[ WARN ]${RESET} $*"; }

OVERALL=0
source server.conf 2>/dev/null || true
PORT="${PORT:-8889}"

echo -e "\n${BOLD}Docker Orchestrator Agent — Health Check${RESET}\n"

command -v docker &>/dev/null && pass "docker CLI found" || fail "docker not found"
[ -d ".venv" ]              && pass ".venv exists"       || fail ".venv missing — run ./build.sh"
[ -f "../shared.conf" ]     && pass "shared.conf found"  || fail "shared.conf not found"

if [ -f "../shared.conf" ]; then
    source ../shared.conf 2>/dev/null || true
    [ -n "${ANTHROPIC_API_KEY:-}" ] \
        && pass "ANTHROPIC_API_KEY set (${ANTHROPIC_API_KEY:0:10}...)" \
        || fail "ANTHROPIC_API_KEY not set"
fi

if curl -sf "http://localhost:${PORT}/health" &>/dev/null; then
    pass "Server is responding on port ${PORT}"
else
    warn "Server not responding on port ${PORT} — run ./start.sh"
fi

if [ -f "docker_agent/memory/docker_status.json" ]; then
    UPDATED=$(python3 -c "import json; d=json.load(open('docker_agent/memory/docker_status.json')); print(d.get('last_updated','?'))" 2>/dev/null)
    pass "docker_status.json exists (updated: $UPDATED)"
else
    warn "docker_status.json not yet written — starts after first monitor cycle"
fi

echo ""
[ "$OVERALL" -eq 0 ] \
    && echo -e "Status: ${GREEN}HEALTHY${RESET}\n" \
    || echo -e "Status: ${RED}UNHEALTHY${RESET} — fix the issues above\n"
exit $OVERALL
