#!/bin/bash

source "$(dirname "$0")/docker_config.sh"

echo "Building image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

echo "Starting container: $CONTAINER_NAME..."
docker run -it \
    --name "$CONTAINER_NAME" \
    -v "$RESOURCES_DIR":/workspace/git-ignore-resources \
    "$IMAGE_NAME"
