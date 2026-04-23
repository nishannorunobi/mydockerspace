#!/bin/bash
# docker_clean.sh — wipes everything Docker: containers, images, volumes, networks, cache.
# Result is a clean slate as if Docker was freshly installed.

BOLD="\033[1m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RESET="\033[0m"

echo -e "${BOLD}${RED}"
echo "╔══════════════════════════════════════════╗"
echo "║         Docker Full Clean                ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${RESET}"
echo -e "${YELLOW}This will permanently remove:${RESET}"
echo "  • All running and stopped containers"
echo "  • All images"
echo "  • All volumes"
echo "  • All custom networks"
echo "  • All build cache"
echo ""
read -rp "Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""

# ─── Stop all running containers ──────────────────────────────────────────────
echo -e "${BOLD}── Stopping all running containers...${RESET}"
running=$(docker ps -q)
if [ -n "$running" ]; then
    docker stop $running
else
    echo "   (none running)"
fi

# ─── Remove all containers ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Removing all containers...${RESET}"
containers=$(docker ps -aq)
if [ -n "$containers" ]; then
    docker rm -f $containers
else
    echo "   (none)"
fi

# ─── Remove all images ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Removing all images...${RESET}"
images=$(docker images -q)
if [ -n "$images" ]; then
    docker rmi -f $images
else
    echo "   (none)"
fi

# ─── Remove all volumes (including named volumes) ────────────────────────────
echo ""
echo -e "${BOLD}── Removing all volumes...${RESET}"
volumes=$(docker volume ls -q)
if [ -n "$volumes" ]; then
    docker volume rm $volumes
else
    echo "   (none)"
fi

# ─── Remove all custom networks ───────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Removing all custom networks...${RESET}"
docker network prune -f

# ─── Clear all build cache ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Clearing build cache...${RESET}"
docker builder prune -af

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✓ Docker is clean. Fresh as a new install.${RESET}"
echo ""
docker system df
