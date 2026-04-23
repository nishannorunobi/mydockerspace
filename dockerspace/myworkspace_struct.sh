#!/bin/bash
# myworkspace_struct.sh — ensures the full workspace directory structure exists.
# Safe to run multiple times. Creates any missing directories.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/workspace.conf"

echo "==> Checking workspace structure at: $WORKSPACE_ROOT"

ensure_dir() {
    local path="$1"
    local label="$2"
    if [ -d "$path" ]; then
        echo "    [ok]     $label"
    else
        mkdir -p "$path"
        echo "    [created] $label"
    fi
}

# ─── Top-level directories ────────────────────────────────────────────────────
ensure_dir "$WORKSPACE_ROOT/.vscode"              ".vscode/"
ensure_dir "$WORKSPACE_ROOT/claude"               "claude/"
ensure_dir "$WORKSPACE_ROOT/dockerspace"          "dockerspace/"
ensure_dir "$WORKSPACE_ROOT/$PROJECTSPACE_DIR"          "$PROJECTSPACE_DIR/          (gitignored)"
ensure_dir "$WORKSPACE_ROOT/$MOUNTSPACE_DIR"            "$MOUNTSPACE_DIR/            (gitignored)"
ensure_dir "$WORKSPACE_ROOT/claude/.claude-config"      "claude/.claude-config/      (gitignored)"

echo "==> Workspace structure OK."
