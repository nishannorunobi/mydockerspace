#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/workspace.conf"

bash "$SCRIPT_DIR/myworkspace_struct.sh"
bash "$SCRIPT_DIR/check_hostdocker.sh" || exit 1

echo "Building image: $IMAGE_NAME..."
docker build --build-arg CONTAINER_WORKDIR="$CONTAINER_WORKDIR" -t "$IMAGE_NAME" "$SCRIPT_DIR"

echo "Starting container: $CONTAINER_NAME..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -v "$WORKSPACE_ROOT":"$CONTAINER_WORKDIR" \
    "$IMAGE_NAME" \
    tail -f /dev/null

# COPY_SSH_FROM_HOST=true:  copies keys here (host side), container script distributes to user ~/.ssh
# COPY_SSH_FROM_HOST=false: nothing to do here, container script generates the key directly
if [ "$COPY_SSH_FROM_HOST" = true ]; then
    echo "Copying SSH keys from host..."
    docker cp ~/.ssh "$CONTAINER_NAME":/root/.ssh
fi

bash "$SCRIPT_DIR/troubleshoot.sh"

echo "Running $CONTAINER_TYPE environment setup..."
docker exec -it "$CONTAINER_NAME" bash "$CONTAINER_WORKDIR/dockerspace/${CONTAINER_TYPE}_container.sh"

echo "Container ready. Dropping into shell..."
docker exec -it "$CONTAINER_NAME" bash
