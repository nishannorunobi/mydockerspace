#!/bin/bash
# start.sh — Start the workspace management agent.
# Usage:
#   ./start.sh                                  # interactive chat
#   ./start.sh "scan and update memory"         # one-shot
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED="\033[31m"; RESET="\033[0m"

[ -d ".venv" ]      || { echo -e "${RED}[ERROR]${RESET} .venv not found. Run ./build.sh first."; exit 1; }
[ -f "agent.conf" ] || { echo -e "${RED}[ERROR]${RESET} agent.conf not found. Run ./build.sh first."; exit 1; }

source agent.conf
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo -e "${RED}[ERROR]${RESET} ANTHROPIC_API_KEY not set in agent.conf"; exit 1; }

if [ $# -gt 0 ]; then
    .venv/bin/python agents/workspace/agent.py "$@"
else
    .venv/bin/python agents/workspace/agent.py
fi
