#!/bin/bash
# Shared library — source this file, do not run it directly.
# Provides: install_packages, setup_user, setup_ssh, setup_git, setup_workspace_group

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/workspace.conf"
source "$SCRIPT_DIR/project.conf"

# ─── Package management ────────────────────────────────────────────────────────

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

install_packages() {
    echo "==> Installing packages..."
    export DEBIAN_FRONTEND=noninteractive
    export TZ=America/New_York
    update_pkg_index
    install_pkg git              "$GIT_VERSION"
    install_pkg build-essential  "$BUILD_ESSENTIAL_VERSION"
    install_pkg curl             "$CURL_VERSION"
    install_pkg wget             "$WGET_VERSION"
    install_pkg vim              "$VIM_VERSION"
    install_pkg unzip            "$UNZIP_VERSION"
    install_pkg openssh-client   "$OPENSSH_CLIENT_VERSION"
    cleanup_pkg_cache
    echo "    Done."
}

# ─── User setup ────────────────────────────────────────────────────────────────

setup_user() {
    local user=$1

    if id "$user" &>/dev/null; then
        echo "==> User '$user' already exists, skipping."
    else
        echo "==> Creating user '$user'..."
        useradd -m -s /bin/bash "$user"
        echo "    Done."
    fi
}

generate_ssh_key() {
    local user=$1
    local ssh_dir="/home/$user/.ssh"
    local key_file="$ssh_dir/id_ed25519"

    mkdir -p "$ssh_dir"
    chmod 700 "$ssh_dir"
    chown "$user":"$user" "$ssh_dir"

    if [ -f "$key_file" ]; then
        echo "==> SSH key for '$user' already exists, skipping."
        return
    fi

    echo "==> Generating SSH key for '$user'..."
    su - "$user" -c "ssh-keygen -t ed25519 -C '$user@mydockerspace' -f '$key_file' -N ''"
    echo "    Done."
    echo "==> Public key for '$user' (add this to GitHub / GitLab):"
    cat "$key_file.pub"
    echo ""
}

copy_ssh_from_host() {
    local user=$1
    local ssh_dir="/home/$user/.ssh"
    local key_file="$ssh_dir/id_ed25519"
    local host_key="/root/.ssh/id_ed25519"

    mkdir -p "$ssh_dir"
    chmod 700 "$ssh_dir"
    chown "$user":"$user" "$ssh_dir"

    if [ -f "$key_file" ]; then
        echo "==> SSH key for '$user' already exists, skipping."
        return
    fi

    if [ ! -f "$host_key" ]; then
        echo "    WARNING: No host key found at $host_key — skipping SSH setup for '$user'."
        return
    fi

    echo "==> Copying SSH key from host for '$user'..."
    cp "$host_key"       "$key_file"
    cp "${host_key}.pub" "${key_file}.pub"
    chown "$user":"$user" "$key_file" "${key_file}.pub"
    chmod 600 "$key_file"
    chmod 644 "${key_file}.pub"
    echo "    Done."
}

setup_git() {
    local user=$1
    local current_name current_email

    current_name=$(su - "$user" -c "git config --global user.name || true")
    current_email=$(su - "$user" -c "git config --global user.email || true")

    if [ -n "$current_name" ] && [ -n "$current_email" ]; then
        echo "==> Git for '$user' already configured as '$current_name' <$current_email>, skipping."
        return
    fi

    if [ -z "${GIT_USER_NAME:-}" ] || [ -z "${GIT_USER_EMAIL:-}" ]; then
        echo "    ERROR: GIT_USER_NAME and GIT_USER_EMAIL must be set in workspace.conf"
        exit 1
    fi

    echo "==> Configuring git for '$user' as '$GIT_USER_NAME' <$GIT_USER_EMAIL>..."
    su - "$user" -c "git config --global user.name '$GIT_USER_NAME'"
    su - "$user" -c "git config --global user.email '$GIT_USER_EMAIL'"
    echo "    Done."
}

setup_project() {
    local user=$1

    if [ -z "${GIT_CLONE_URL:-}" ]; then
        echo "==> GIT_CLONE_URL not set, skipping project clone."
        return
    fi

    local repo_name
    repo_name=$(basename "$GIT_CLONE_URL" .git)
    local clone_name="${PROJECT_NAME:-$repo_name}"
    local clone_path="$CONTAINER_WORKDIR/$PROJECTSPACE_DIR/$clone_name"

    if [ -d "$clone_path/.git" ]; then
        echo "==> Project '$clone_name' already cloned, skipping."
        return
    fi

    echo "==> Adding GitHub to known_hosts for '$user'..."
    su - "$user" -c "mkdir -p ~/.ssh && ssh-keyscan -H github.com >> ~/.ssh/known_hosts 2>/dev/null"

    echo "==> Cloning '$GIT_CLONE_URL' into $PROJECTSPACE_DIR/$clone_name..."
    mkdir -p "$clone_path"
    chown "$user":"$user" "$clone_path"
    su - "$user" -c "git clone '$GIT_CLONE_URL' '$clone_path'"
    echo "    Done."
}

setup_workspace_group() {
    local user=$1
    local group="dockerusergroup"

    if getent group "$group" &>/dev/null; then
        echo "==> Group '$group' already exists, skipping creation."
    else
        echo "==> Creating group '$group'..."
        groupadd "$group"
        echo "    Done."
    fi

    if id -nG "$user" 2>/dev/null | grep -qw "$group"; then
        echo "==> '$user' already in '$group', skipping."
    else
        echo "==> Adding '$user' to '$group'..."
        usermod -aG "$group" "$user"
        echo "    Done."
    fi

    chown :"$group" "$CONTAINER_WORKDIR"
    chmod g+ws "$CONTAINER_WORKDIR"
    echo "==> $CONTAINER_WORKDIR is group-writable by '$group'."
}
