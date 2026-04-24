#!/bin/bash
# troubleshoot.sh — fixes common workspace issues.
# Safe to run any time, on the host, with or without the container running.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/project.conf"
source "$SCRIPT_DIR/workspace.conf"

echo "==> Running troubleshoot fixes for: $WORKSPACE_ROOT"
echo ""

# ─── Fix 1: Workspace ownership ───────────────────────────────────────────────
# Docker runs as root and can chown the volume-mounted workspace,
# causing 'git: detected dubious ownership' on the host.

echo "── Fix: Workspace ownership"
sudo chown -R "$USER":"$USER" "$WORKSPACE_ROOT"
echo "   Ownership restored to $USER."

# ─── Fix 2: mountspace/ permissions ───────────────────────────────────────────

echo ""
echo "── Fix: $MOUNTSPACE_DIR/ permissions"
mkdir -p "$WORKSPACE_ROOT/$MOUNTSPACE_DIR"
sudo chown -R "$USER":"$USER" "$WORKSPACE_ROOT/$MOUNTSPACE_DIR"
echo "   $MOUNTSPACE_DIR/ is ready."

# ─── Fix 3: Git safe.directory ────────────────────────────────────────────────
# If git still refuses after chown (e.g. multi-user setup), register as safe.

echo ""
echo "── Fix: git safe.directory"
if git -C "$WORKSPACE_ROOT" status &>/dev/null; then
    echo "   git is happy, no change needed."
else
    git config --global --add safe.directory "$WORKSPACE_ROOT"
    echo "   Added $WORKSPACE_ROOT to git safe.directory."
fi

echo ""
echo "==> Done. Try 'git status' and 'bash dockerspace/start.sh' now."
