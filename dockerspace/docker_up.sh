#!/bin/bash

echo "==> Checking Docker status..."

if systemctl is-active --quiet docker.service; then
    echo "    Docker is already running."
else
    echo "==> Starting Docker service..."
    sudo systemctl start docker.socket docker.service

    echo -n "    Waiting for Docker to be ready"
    for i in $(seq 1 10); do
        if systemctl is-active --quiet docker.service && docker info &>/dev/null; then
            echo " ready."
            break
        fi
        echo -n "."
        sleep 1
    done

    if ! systemctl is-active --quiet docker.service; then
        echo ""
        echo "    ERROR: Docker failed to start."
        systemctl status docker.service --no-pager
        exit 1
    fi
fi

echo ""
docker version
echo ""
echo "==> Docker is up. You can now run your other scripts."
