#!/bin/bash

source "$(dirname "$0")/docker_config.sh"

echo "Stopping container: $CONTAINER_NAME..."
docker stop "$CONTAINER_NAME" 2>/dev/null

echo "Removing container: $CONTAINER_NAME..."
docker rm "$CONTAINER_NAME" 2>/dev/null

echo "Removing image: $IMAGE_NAME..."
docker rmi "$IMAGE_NAME" 2>/dev/null

echo "Done."
