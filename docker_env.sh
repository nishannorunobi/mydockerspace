#!/bin/bash
# Run this INSIDE the container to install OS-level dependencies

apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    vim \
    unzip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

echo "Environment setup complete."
