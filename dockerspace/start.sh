#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/project.conf"
source "$SCRIPT_DIR/workspace.conf"

bash "$WORKSPACE_ROOT/myworkspace_struct.sh"

HOST_PLUGINS="$HOME/.docker/cli-plugins"
SHARED_PLUGINS="$WORKSPACE_ROOT/$DOCKER_PLUGINS_DIR"
mkdir -p "$HOME/.docker"
if [ -L "$HOST_PLUGINS" ]; then
    echo "Host Docker plugins already symlinked, skipping."
elif [ -e "$HOST_PLUGINS" ]; then
    echo "WARNING: $HOST_PLUGINS exists and is not a symlink — skipping host Docker plugins link."
else
    ln -s "$SHARED_PLUGINS" "$HOST_PLUGINS"
    echo "Linked host ~/.docker/cli-plugins → $DOCKER_PLUGINS_DIR"
fi

if [ "${COPY_VSCODE_EXTENSIONS:-false}" = true ]; then
    HOST_EXTS="$HOME/.vscode/extensions"
    SHARED_EXTS="$WORKSPACE_ROOT/$VSCODE_EXTENSIONS_DIR"
    if [ -d "$HOST_EXTS" ]; then
        echo "Copying VS Code extensions from host..."
        cp -rn "$HOST_EXTS/." "$SHARED_EXTS/"
        echo "    Done."
    else
        echo "WARNING: $HOST_EXTS not found — skipping VS Code extensions copy."
    fi
fi

bash "$SCRIPT_DIR/check_hostdocker.sh" || exit 1

FULL_IMAGE="$IMAGE_NAME:$IMAGE_VERSION"

if docker image inspect "$FULL_IMAGE" &>/dev/null; then
    echo "Image $FULL_IMAGE already exists, skipping build."
else
    echo "Building image $FULL_IMAGE..."
    docker build \
        --build-arg BASE_IMAGE="${BASE_IMAGE:-ubuntu:24.04}" \
        --build-arg CONTAINER_WORKDIR="$CONTAINER_WORKDIR" \
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
fi

echo "Running $CONTAINER_TYPE environment setup..."
docker exec "$CONTAINER_NAME" bash "$CONTAINER_WORKDIR/dockerspace/${CONTAINER_TYPE}_container.sh"

echo "Container ready. Dropping into shell..."
docker exec -it "$CONTAINER_NAME" bash
