#!/bin/bash
# build.sh — Set up agent-orchestrator venv and install dependencies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BOLD="\033[1m"; GREEN="\033[32m"; YELLOW="\033[33m"; CYAN="\033[36m"; RED="\033[31m"; RESET="\033[0m"

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[ OK ]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
fail()    { echo -e "${RED}[FAIL]${RESET}  $*" >&2; exit 1; }

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Agent Orchestrator — Build             ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}\n"

command -v python3 &>/dev/null || fail "python3 not found."
info "Python $(python3 --version 2>&1 | awk '{print $2}') found"

info "Removing old virtual environment..."
rm -rf .venv
info "Creating virtual environment..."
python3 -m venv .venv
success "Virtual environment created"

info "Installing dependencies..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
success "Dependencies installed"

[ -f "../shared.conf" ] \
    && success "shared.conf found" \
    || warn "shared.conf not found at agents/shared.conf — set ANTHROPIC_API_KEY there"

mkdir -p memory
success "memory/ directory ready"

echo -e "\n${GREEN}Build complete.${RESET}"
echo -e "  Run   : ${BOLD}./start_web.sh${RESET}\n"
