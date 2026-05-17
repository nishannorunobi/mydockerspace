#!/bin/bash
# Stop the doc-agent process inside plane-aio via docker exec.
set -euo pipefail

CONTAINER="plane-aio"

if ! docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[WARN] Container $CONTAINER is not running — nothing to stop."
    exit 0
fi

docker exec "$CONTAINER" bash -c \
    "pkill -f '[u]vicorn server:app' 2>/dev/null \
     && echo '[OK] Doc agent stopped.' \
     || echo '[WARN] No running doc-agent found.'"
