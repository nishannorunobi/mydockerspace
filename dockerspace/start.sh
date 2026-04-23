#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/workspace.conf"

bash "$SCRIPT_DIR/myworkspace_struct.sh"
bash "$SCRIPT_DIR/check_hostdocker.sh" || exit 1

FULL_IMAGE="$IMAGE_NAME:$IMAGE_VERSION"

if docker image inspect "$FULL_IMAGE" &>/dev/null; then
    echo "Image $FULL_IMAGE already exists, skipping build."
else
    echo "Building image $FULL_IMAGE..."
    docker build --build-arg CONTAINER_WORKDIR="$CONTAINER_WORKDIR" \
        -t "$FULL_IMAGE" "$SCRIPT_DIR"
fi

if [ "${FORCE_RECREATE_CONTAINER:-false}" = true ]; then
    echo "Force recreate: removing existing container $CONTAINER_NAME..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm   "$CONTAINER_NAME" 2>/dev/null || true
fi

if docker container inspect "$CONTAINER_NAME" &>/dev/null; then
    echo "Container $CONTAINER_NAME already exists, starting it..."
    docker start "$CONTAINER_NAME"
else
    echo "Creating new container: $CONTAINER_NAME..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        -v "$WORKSPACE_ROOT":"$CONTAINER_WORKDIR" \
        "$FULL_IMAGE" \
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
fi

echo "Container ready. Dropping into shell..."
docker exec -it "$CONTAINER_NAME" bash
