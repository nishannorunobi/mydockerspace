#!/bin/bash
# build.sh — Set up docker-manager-agent venv and install dependencies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN="\033[32m"; RED="\033[31m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
ok()   { echo -e "${GREEN}[  OK  ]${RESET} $*"; }
fail() { echo -e "${RED}[ FAIL ]${RESET} $*" >&2; exit 1; }
info() { echo -e "${CYAN}[ INFO ]${RESET} $*"; }

echo -e "\n${BOLD}Docker Orchestrator Agent — Build${RESET}\n"

command -v python3 &>/dev/null || fail "python3 not found"
command -v docker  &>/dev/null || fail "docker not found"
ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"
ok "docker $(docker --version | awk '{print $3}' | tr -d ',')"

info "Creating virtualenv..."
python3 -m venv .venv
ok ".venv created"

info "Installing dependencies..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
ok "Dependencies installed"

mkdir -p docker_agent/memory
ok "memory/ directory ready"

echo -e "\n${GREEN}Build complete.${RESET} Run ./start.sh to start.\n"
