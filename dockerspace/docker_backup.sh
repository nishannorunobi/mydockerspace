#!/bin/bash
# docker_backup.sh — commits the running container's state to a new versioned image.
# Increments the minor version (e.g. 1.0 → 1.1), updates workspace.conf, and commits.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/project.conf"
source "$SCRIPT_DIR/workspace.conf"

if ! docker container inspect "$CONTAINER_NAME" &>/dev/null; then
    echo "ERROR: Container '$CONTAINER_NAME' is not running. Start it first with start.sh."
    exit 1
fi

IFS='.' read -r major minor <<< "$IMAGE_VERSION"
NEW_VERSION="$major.$((minor + 1))"
NEW_IMAGE="$IMAGE_NAME:$NEW_VERSION"

echo "Committing '$CONTAINER_NAME' → '$NEW_IMAGE'..."
docker commit "$CONTAINER_NAME" "$NEW_IMAGE"

sed -i "s/^\(IMAGE_VERSION=\"\)[^\"]*\"/\1$NEW_VERSION\"/" "$SCRIPT_DIR/workspace.conf"
echo "Updated IMAGE_VERSION to '$NEW_VERSION' in workspace.conf."
echo "Done."
