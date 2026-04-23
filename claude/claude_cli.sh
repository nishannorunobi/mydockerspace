#!/bin/bash
# claude_cli.sh — Claude Code CLI setup.
# Can be sourced by container scripts or run directly from inside the claude/ folder.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../dockerspace/workspace.conf"
source "$SCRIPT_DIR/claude.conf"

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

CLAUDE_INSTALL_DIR="$SCRIPT_DIR"
CLAUDE_CONFIG_DIR="$SCRIPT_DIR/.claude-config"

is_inside_container() {
    [ -f "/.dockerenv" ]
}

setup_claude_config_host() {
    mkdir -p "$CLAUDE_CONFIG_DIR"

    if [ -L "$HOME/.claude" ]; then
        echo "==> Claude config symlink already set up, skipping."
        return
    fi

    if [ -d "$HOME/.claude" ]; then
        if [ "${COPY_CLAUDE_CONFIG:-false}" = true ]; then
            echo "==> Migrating ~/.claude to shared config dir..."
            cp -r "$HOME/.claude/." "$CLAUDE_CONFIG_DIR/"
            chmod 600 "$CLAUDE_CONFIG_DIR/.credentials.json" 2>/dev/null || true
            rm -rf "$HOME/.claude"
            echo "    Done."
        else
            echo "==> WARNING: ~/.claude is a real directory. Set COPY_CLAUDE_CONFIG=true in workspace.conf to migrate it to the shared config dir."
            return
        fi
    fi

    ln -sf "$CLAUDE_CONFIG_DIR" "$HOME/.claude"
    echo "==> ~/.claude linked to $CLAUDE_CONFIG_DIR"
}

setup_claude_config_container() {
    local user=$1
    local config_dir="$CONTAINER_WORKDIR/claude/.claude-config"
    local home_dir
    home_dir=$(getent passwd "$user" | cut -d: -f6)
    local link="$home_dir/.claude"

    mkdir -p "$config_dir"
    chown -R "$user":"$user" "$config_dir"

    if [ -L "$link" ]; then
        echo "==> Claude config for '$user' already linked, skipping."
        return
    fi

    echo "==> Linking Claude config for '$user' to shared config dir..."
    ln -sf "$config_dir" "$link"
    chown -h "$user":"$user" "$link"
    echo "    Done."
}

setup_claude_config() {
    if is_inside_container; then
        setup_claude_config_container "${1:-$(whoami)}"
    else
        setup_claude_config_host
    fi
}

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
    setup_claude_config
    exec "$CLAUDE_INSTALL_DIR/node_modules/.bin/claude"
fi
