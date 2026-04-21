#!/bin/bash
# Run this INSIDE the container to install OS-level dependencies

source "$(dirname "$0")/docker_os.env"

install_pkg() {
    local pkg=$1
    local version=$2

    case "$PKG_MANAGER" in
        apt)
            if [ "$version" = "latest" ]; then
                apt-get install -y "$pkg"
            else
                apt-get install -y "$pkg=$version"
            fi
            ;;
        yum)
            if [ "$version" = "latest" ]; then
                yum install -y "$pkg"
            else
                yum install -y "$pkg-$version"
            fi
            ;;
        dnf)
            if [ "$version" = "latest" ]; then
                dnf install -y "$pkg"
            else
                dnf install -y "$pkg-$version"
            fi
            ;;
        apk)
            if [ "$version" = "latest" ]; then
                apk add --no-cache "$pkg"
            else
                apk add --no-cache "$pkg=$version"
            fi
            ;;
        *)
            echo "Unknown PKG_MANAGER: $PKG_MANAGER"
            exit 1
            ;;
    esac
}

update_pkg_index() {
    case "$PKG_MANAGER" in
        apt) apt-get update ;;
        yum) yum makecache -y ;;
        dnf) dnf makecache -y ;;
        apk) apk update ;;
    esac
}

cleanup_pkg_cache() {
    case "$PKG_MANAGER" in
        apt) rm -rf /var/lib/apt/lists/* ;;
        yum) yum clean all ;;
        dnf) dnf clean all ;;
        apk) rm -rf /var/cache/apk/* ;;
    esac
}

setup_env() {
    update_pkg_index

    install_pkg git "$GIT_VERSION"
    install_pkg vim "$VIM_VERSION"
    install_pkg curl "$CURL_VERSION"
    install_pkg wget "$WGET_VERSION"
    install_pkg unzip "$UNZIP_VERSION"
    install_pkg build-essential "$BUILD_ESSENTIAL_VERSION"

    cleanup_pkg_cache

    echo "Environment setup complete."
}

setup_env
