#!/bin/bash

PORTAINER_CONTAINER="portainer"
PORTAINER_IMAGE="portainer/portainer-ce:latest"
PORTAINER_PORT="9000"
PORTAINER_VOLUME="portainer_data"

if docker inspect -f '{{.State.Status}}' "$PORTAINER_CONTAINER" 2>/dev/null | grep -q "running"; then
    echo "==> Portainer is already running."
    echo "    UI: http://localhost:$PORTAINER_PORT"
    exit 0
fi

if docker container inspect "$PORTAINER_CONTAINER" &>/dev/null; then
    echo "==> Starting existing Portainer container..."
    docker start "$PORTAINER_CONTAINER"
else
    echo "==> Creating and starting Portainer..."
    docker run -d \
        --name "$PORTAINER_CONTAINER" \
        --restart=unless-stopped \
        -p "$PORTAINER_PORT":9000 \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v "$PORTAINER_VOLUME":/data \
        "$PORTAINER_IMAGE"
fi

echo "    Done."
echo "    UI: http://localhost:$PORTAINER_PORT"
admin user name pass:
user: admin, pass: portaineradmin123
