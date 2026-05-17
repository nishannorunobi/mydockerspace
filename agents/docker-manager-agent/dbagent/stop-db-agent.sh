#!/bin/bash
# Stop the db-agent process inside mypostgresql_db-container via docker exec.
set -euo pipefail

CONTAINER="mypostgresql_db-container"

if ! docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[WARN] Container $CONTAINER is not running — nothing to stop."
    exit 0
fi

docker exec "$CONTAINER" bash -c \
    "pkill -f '[u]vicorn server:app' 2>/dev/null \
     && echo '[OK] DB agent stopped.' \
     || echo '[WARN] No running db-agent found.'"
