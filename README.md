# mydockerspace

A generic Dockerized development workspace. Only Docker needed on the host — everything else lives inside the container.

---

## Quick Start

**1. Configure `dockerspace/workspace.conf`**
```bash
CONTAINER_TYPE="dev"                          # dev | test | prod
PKG_MANAGER="apt"                             # apt | yum | dnf | apk
GIT_USER_NAME="Your Name"
GIT_USER_EMAIL="your@email.com"
COPY_SSH_FROM_HOST=true                       # reuse host SSH key
GIT_CLONE_URL="git@github.com:you/repo.git"  # auto-cloned into projectspace/
```

**2. Start**
```bash
bash dockerspace/start.sh
```
Checks Docker, creates missing directories, builds the image, sets up the container, and clones your project automatically.

**3. Enter the container**
```bash
docker exec -it mydockerspace-container bash
su - devuser   # or testuser / produser
```

**4. Stop and clean up**
```bash
bash dockerspace/stop.sh
```

---

## Container Types

| Type | User |
|---|---|
| `dev` | devuser |
| `test` | testuser |
| `prod` | produser |

---

## SSH Keys

| Mode | Behaviour |
|---|---|
| `COPY_SSH_FROM_HOST=true` | Reuses your host `~/.ssh/id_ed25519` — no GitHub re-auth needed |
| `COPY_SSH_FROM_HOST=false` | Generates a new keypair inside the container — public key printed at the end |

---

## Directory Structure

```
myworkspace/
├── dockerspace/      ← all scripts and Docker config
├── claude/           ← Claude Code CLI (optional)
├── projectspace/     ← your cloned project lives here (gitignored)
└── mountspace/       ← local files/media, never committed (gitignored)
```

---

## Troubleshooting

If you see `git: detected dubious ownership` or permission errors after a container run:
```bash
bash dockerspace/troubleshoot.sh
```

To check your Docker environment at a glance:
```bash
bash dockerspace/docker_dashboard.sh
```
