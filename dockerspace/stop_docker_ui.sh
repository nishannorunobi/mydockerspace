#!/bin/bash

PORTAINER_CONTAINER="portainer"

echo "==> Stopping Portainer..."
docker stop "$PORTAINER_CONTAINER" 2>/dev/null && echo "    Done." || echo "    Not running."
