#!/bin/bash
set -euo pipefail

CLAUDE_BIN="$(dirname "${BASH_SOURCE[0]}")/node_modules/.bin/claude"

if [ ! -f "$CLAUDE_BIN" ]; then
    echo "Claude Code CLI not installed. Run ./claude_cli.sh first."
    exit 1
fi

exec "$CLAUDE_BIN"
