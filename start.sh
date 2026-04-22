#!/bin/bash

source "$(dirname "$0")/workspace.conf"

echo "Building image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

echo "Starting container: $CONTAINER_NAME..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -v "$(pwd)/git-ignore-resources":/mydockerspace/git-ignore-resources \
    -v "$(pwd)/claude":/mydockerspace/claude \
    "$IMAGE_NAME" \
    tail -f /dev/null

# COPY_SSH_FROM_HOST=true:  copies keys here (host side), container script distributes to user ~/.ssh
# COPY_SSH_FROM_HOST=false: nothing to do here, container script generates the key directly
if [ "$COPY_SSH_FROM_HOST" = true ]; then
    echo "Copying SSH keys from host..."
    docker cp ~/.ssh "$CONTAINER_NAME":/root/.ssh
fi

if [ "$COPY_VSCODE_SETTINGS" = true ]; then
    echo "Copying VS Code settings..."
    docker cp .vscode/settings.json "$CONTAINER_NAME":/mydockerspace/.vscode/settings.json
fi

echo "Running $CONTAINER_TYPE environment setup..."
docker exec -it "$CONTAINER_NAME" bash /mydockerspace/${CONTAINER_TYPE}_container.sh

bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/permission.sh"
