#!/bin/bash

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/project.conf"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/workspace.conf"

echo "Stopping container: $CONTAINER_NAME..."
docker stop "$CONTAINER_NAME" 2>/dev/null

echo "Removing container: $CONTAINER_NAME..."
docker rm "$CONTAINER_NAME" 2>/dev/null

if [ "$REMOVE_IMAGE_ON_STOP" = true ]; then
    echo "Removing image: $IMAGE_NAME:$IMAGE_VERSION..."
    docker rmi "$IMAGE_NAME:$IMAGE_VERSION" 2>/dev/null
fi

if [ "$CLEAN_VSCODE_CACHE_ON_STOP" = true ]; then
    echo "Clearing VS Code remote container cache..."
    rm -rf ~/.config/Code/User/globalStorage/ms-vscode-remote.remote-containers
fi

bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/troubleshoot.sh"

echo "Done."
