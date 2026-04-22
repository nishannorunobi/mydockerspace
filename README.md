# mydockerspace

A generic Dockerized development workspace. Only Docker needed on the host.

## Quick Start

**1. Configure `workspace.conf`**
```bash
CONTAINER_TYPE="dev"           # dev | test | prod
PKG_MANAGER="apt"              # apt | yum | dnf | apk
GIT_USER_NAME="Your Name"
GIT_USER_EMAIL="your@email.com"
SSH_KEY_MODE="copy_from_host"  # copy_from_host | generate
```

**2. Start**
```bash
bash start.sh
```
Builds the image, starts the container, and sets up the environment automatically.

**3. Enter the container**
```bash
docker exec -it mydockerspace-container bash
su - devuser   # or testuser / produser
```

**4. Stop and clean up**
```bash
bash stop.sh
```

## Container Types

| Type | User |
|---|---|
| `dev` | devuser |
| `test` | testuser |
| `prod` | produser |

## SSH Keys

- `copy_from_host` — reuses your host `~/.ssh/id_ed25519`, no GitHub re-auth needed
- `generate` — creates a new keypair inside the container, public key is printed at the end
