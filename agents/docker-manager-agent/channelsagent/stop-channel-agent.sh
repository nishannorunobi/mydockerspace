#!/bin/bash
# Stop the channel-agent process inside mychannels-rabbitmq via docker exec.
set -euo pipefail

CONTAINER="mychannels-rabbitmq"
AGENT_DIR="/channel-agent"

if ! docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[WARN] Container $CONTAINER is not running."
    exit 0
fi

docker exec "$CONTAINER" sh -c \
    "pkill -f '[u]vicorn server:app' 2>/dev/null && echo '[OK] Channel agent stopped.' || echo '[WARN] No running channel agent found.'"
