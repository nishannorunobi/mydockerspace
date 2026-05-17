#!/bin/bash
# Stop the cache-agent process inside mycache-redis via docker exec.
set -euo pipefail

CONTAINER="mycache-redis"

if ! docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[WARN] Container $CONTAINER is not running — nothing to stop."
    exit 0
fi

docker exec "$CONTAINER" sh -c \
    "pkill -f '[u]vicorn server:app' 2>/dev/null \
     && echo '[OK] Cache agent stopped.' \
     || echo '[WARN] No running cache-agent found.'"
