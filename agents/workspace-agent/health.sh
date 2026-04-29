#!/bin/bash
# health.sh — Check workspace agent is ready to run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"

pass() { echo -e "${GREEN}[  OK  ]${RESET} $*"; }
fail() { echo -e "${RED}[ FAIL ]${RESET} $*"; OVERALL=1; }
warn() { echo -e "${YELLOW}[ WARN ]${RESET} $*"; }
info() { echo -e "         ${DIM}$*${RESET}"; }

OVERALL=0

echo -e "\n${BOLD}Workspace Management Agent — Health Check${RESET}\n"

command -v python3 &>/dev/null \
    && pass "Python $(python3 --version 2>&1 | awk '{print $2}')" \
    || fail "python3 not found"

[ -d ".venv" ] && pass ".venv exists" || fail ".venv missing — run ./build.sh"

if [ -d ".venv" ]; then
    MISSING=""
    for pkg in anthropic dotenv; do
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

if [ -d "workspace/memory" ]; then
    FILES=$(ls workspace/memory/ 2>/dev/null | wc -l)
    pass "workspace/memory/ exists ($FILES file(s))"
    [ "$FILES" -gt 0 ] && info "$(ls workspace/memory/)"
else
    warn "workspace/memory/ not found — will be created on first run"
fi

if git -C ../.. rev-parse --git-dir &>/dev/null; then
    BRANCH=$(git -C ../.. branch --show-current 2>/dev/null)
    pass "Workspace git repo on branch: $BRANCH"
else
    warn "Workspace is not a git repo — git tools will be limited"
fi

if pgrep -f "workspace/agent.py --daemon" &>/dev/null; then
    pass "Agent daemon is running (PID $(pgrep -f "workspace/agent.py --daemon" | head -1))"
else
    warn "Agent daemon is not running — click Start in the dashboard or run ./start_daemon.sh"
fi

echo ""
echo "──────────────────────────────────────────"
if [ "$OVERALL" -eq 0 ]; then
    echo -e "Status: ${GREEN}HEALTHY${RESET}"
else
    echo -e "Status: ${RED}UNHEALTHY${RESET} — fix the issues above"
fi
echo ""
exit $OVERALL
