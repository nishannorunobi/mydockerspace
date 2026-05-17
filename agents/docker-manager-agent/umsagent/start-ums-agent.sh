#!/bin/bash
# Start the ums-agent process inside ums-app via docker exec.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER="ums-app"
AGENT_DIR="/ums/ums-agent"
SHARED_CONF="$SCRIPT_DIR/../../shared.conf"

if ! docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[ERROR] Container $CONTAINER is not running." >&2
    exit 1
fi

# Build venv if missing or its Python interpreter is broken
if ! docker exec "$CONTAINER" bash -c "$AGENT_DIR/.venv/bin/python3 --version" &>/dev/null; then
    echo "[INFO] Building ums-agent venv inside container..."
    docker exec "$CONTAINER" rm -rf "$AGENT_DIR/.venv"
    docker exec "$CONTAINER" bash "$AGENT_DIR/build.sh"
fi

# Inject API key from shared.conf into the container's agent.conf (idempotent)
if [ -f "$SHARED_CONF" ]; then
    source "$SHARED_CONF"
    docker exec "$CONTAINER" bash -c "
        grep -q 'ANTHROPIC_API_KEY' $AGENT_DIR/agent.conf 2>/dev/null \
            && sed -i 's|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY|' $AGENT_DIR/agent.conf \
            || echo 'ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY' >> $AGENT_DIR/agent.conf"
fi

# Kill any existing ums-agent uvicorn (idempotent).
# The [u]vicorn bracket trick prevents pkill from matching its own command line.
docker exec "$CONTAINER" bash -c \
    "pkill -f '[u]vicorn server:app' 2>/dev/null; sleep 0.3; echo ok"

# Start fresh in background, sourcing agent.conf for ANTHROPIC_API_KEY / PORT
docker exec -d "$CONTAINER" bash -c \
    "cd $AGENT_DIR && source agent.conf && \
     .venv/bin/uvicorn server:app \
        --host 0.0.0.0 --port \${PORT:-8891} \
        --no-use-colors --access-log \
        >> memory/server.log 2>&1"

echo "[OK] UMS agent started inside $CONTAINER."
