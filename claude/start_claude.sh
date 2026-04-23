#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/claude_cli.sh"

# Ensure config is migrated to shared dir and ~/.claude is symlinked (host)
# or symlinked to shared dir (container) — idempotent, safe to run every time
setup_claude_config

if [ ! -f "$CLAUDE_INSTALL_DIR/node_modules/.bin/claude" ]; then
    echo "Claude Code CLI not installed. Run ./claude_cli.sh first."
    exit 1
fi

exec "$CLAUDE_INSTALL_DIR/node_modules/.bin/claude"
