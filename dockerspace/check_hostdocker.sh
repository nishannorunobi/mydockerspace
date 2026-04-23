#!/bin/bash
# check_hostdocker.sh — ensures Docker is installed and the daemon is running.
# Installs Docker if missing, then starts the daemon if stopped.
# Exits non-zero if either step cannot be completed.

TIMEOUT=60   # seconds to wait for daemon to become ready

# ─── Install ───────────────────────────────────────────────────────────────────

is_docker_installed() {
    command -v docker &>/dev/null
}

install_docker_linux() {
    if ! command -v curl &>/dev/null; then
        echo "ERROR: 'curl' is required to download the Docker installer but was not found."
        echo "       Install curl first (e.g. sudo apt-get install -y curl) then re-run."
        exit 1
    fi

    echo "==> Downloading and running the official Docker install script (get.docker.com)..."
    curl -fsSL https://get.docker.com | sudo sh

    # Add the current user to the docker group so future docker calls don't need sudo
    if id "$USER" &>/dev/null && ! id -nG "$USER" | grep -qw docker; then
        echo "==> Adding '$USER' to the 'docker' group..."
        sudo usermod -aG docker "$USER"
        echo "    NOTE: Log out and back in (or run 'newgrp docker') for group membership to take effect."
    fi
}

install_docker_macos() {
    if command -v brew &>/dev/null; then
        echo "==> Installing Docker Desktop via Homebrew..."
        brew install --cask docker
        echo "==> Launching Docker Desktop..."
        open -a Docker
    else
        echo "ERROR: Homebrew is not installed."
        echo "       Install Homebrew from https://brew.sh, then re-run."
        echo "       Or install Docker Desktop manually from https://www.docker.com/products/docker-desktop"
        exit 1
    fi
}

install_docker() {
    echo "==> Docker is not installed. Installing..."
    case "$(uname -s)" in
        Linux)  install_docker_linux ;;
        Darwin) install_docker_macos ;;
        *)
            echo "ERROR: Unsupported OS '$(uname -s)'. Install Docker manually from https://docs.docker.com/get-docker/"
            exit 1
            ;;
    esac
    echo "==> Docker installed."
}

# ─── Daemon ────────────────────────────────────────────────────────────────────

is_daemon_running() {
    docker info &>/dev/null
}

start_daemon_linux() {
    if command -v systemctl &>/dev/null && systemctl list-units --type=service &>/dev/null 2>&1; then
        echo "==> Starting Docker daemon via systemctl..."
        sudo systemctl start docker
    elif command -v service &>/dev/null; then
        echo "==> Starting Docker daemon via service..."
        sudo service docker start
    else
        echo "ERROR: Cannot detect init system. Start the Docker daemon manually and re-run."
        exit 1
    fi
}

start_daemon_macos() {
    echo "==> Starting Docker Desktop on macOS..."
    open -a Docker
}

start_daemon() {
    case "$(uname -s)" in
        Linux)  start_daemon_linux ;;
        Darwin) start_daemon_macos ;;
        *)
            echo "ERROR: Unsupported OS '$(uname -s)'. Start the Docker daemon manually and re-run."
            exit 1
            ;;
    esac
}

wait_for_daemon() {
    local elapsed=0
    echo -n "==> Waiting for Docker daemon"
    while ! is_daemon_running; do
        if [ "$elapsed" -ge "$TIMEOUT" ]; then
            echo ""
            echo "ERROR: Docker daemon did not become ready within ${TIMEOUT}s."
            exit 1
        fi
        echo -n "."
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo " ready."
}

# ─── Main ─────────────────────────────────────────────────────────────────────

if ! is_docker_installed; then
    install_docker
fi

if is_daemon_running; then
    echo "==> Docker daemon is running."
    exit 0
fi

echo "==> Docker daemon is not running."
start_daemon
wait_for_daemon
