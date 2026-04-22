#!/bin/bash
set -euo pipefail
# Prod environment setup — runs INSIDE the container. Safe to run multiple times.

source "$(dirname "${BASH_SOURCE[0]}")/functions.sh"
source "$(dirname "${BASH_SOURCE[0]}")/claude/claude_cli.sh"

USER="produser"

echo "====== Prod Container Setup ======"
install_packages
echo ""
echo "──── Setting up $USER ────"
setup_user            "$USER"
if [ "$COPY_SSH_FROM_HOST" = true ]; then
    copy_ssh_from_host "$USER"
else
    generate_ssh_key   "$USER"
fi
setup_git             "$USER"
setup_workspace_group "$USER"

if [ "$INSTALL_CLAUDE_CLI" = true ]; then
    echo ""
    echo "──── Setting up Claude Code CLI ────"
    install_node
    install_claude_cli
fi

echo ""
echo "Prod environment ready. Switch to: su - $USER"
