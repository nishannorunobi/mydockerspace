#!/bin/bash
set -euo pipefail
# Test environment setup — runs INSIDE the container. Safe to run multiple times.

source "$(dirname "${BASH_SOURCE[0]}")/functions.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../claude/claude_cli.sh"

USER="testuser"

echo "====== Test Container Setup ======"
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
    setup_claude_config_container "$USER"
fi

echo ""
echo "──── Cloning project ────"
setup_project "$USER"

echo ""
echo "Test environment ready. Switch to: su - $USER"
