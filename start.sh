#!/bin/bash

source "$(dirname "$0")/docker_config.sh"

echo "Building image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

echo "Starting container: $CONTAINER_NAME..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -v "$RESOURCES_DIR":/mydockerspace/git-ignore-resources \
    "$IMAGE_NAME" \
    tail -f /dev/null

echo "Copying VS Code settings..."
docker exec "$CONTAINER_NAME" mkdir -p /mydockerspace/.vscode
docker cp .vscode/settings.json "$CONTAINER_NAME":/mydockerspace/.vscode/settings.json

echo "Container started. To enter: docker exec -it $CONTAINER_NAME bash"
