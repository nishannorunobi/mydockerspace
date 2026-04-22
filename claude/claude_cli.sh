#!/bin/bash
# claude_cli.sh — Claude Code CLI setup.
# Can be sourced by container scripts or run directly from inside the claude/ folder.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../workspace.conf"

install_node() {
    if command -v node &>/dev/null; then
        echo "==> Node.js already installed, skipping."
        return
    fi

    echo "==> Installing Node.js..."
    case "$PKG_MANAGER" in
        apt)
            apt-get update
            if [ "$NODE_VERSION" = "latest" ]; then
                apt-get install -y nodejs npm
            else
                apt-get install -y "nodejs=$NODE_VERSION" npm
            fi
            ;;
        apk)
            if [ "$NODE_VERSION" = "latest" ]; then
                apk add --no-cache nodejs npm
            else
                apk add --no-cache "nodejs=$NODE_VERSION" npm
            fi
            ;;
        yum|dnf)
            if [ "$NODE_VERSION" = "latest" ]; then
                $PKG_MANAGER install -y nodejs npm
            else
                $PKG_MANAGER install -y "nodejs-$NODE_VERSION" npm
            fi
            ;;
        *)
            echo "Unknown PKG_MANAGER: $PKG_MANAGER"
            exit 1
            ;;
    esac
    echo "    Done."
}

CLAUDE_INSTALL_DIR="/mydockerspace/claude"

install_claude_cli() {
    if [ -f "$CLAUDE_INSTALL_DIR/node_modules/.bin/claude" ]; then
        echo "==> Claude Code CLI already installed, skipping."
        return
    fi

    echo "==> Installing Claude Code CLI into $CLAUDE_INSTALL_DIR..."
    npm install --prefix "$CLAUDE_INSTALL_DIR" @anthropic-ai/claude-code
    echo "    Done."
    echo "==> Run Claude with: $CLAUDE_INSTALL_DIR/node_modules/.bin/claude"
}


# ─── Main (only runs when executed directly, not when sourced) ─────────────────

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
    install_node
    install_claude_cli
fi
