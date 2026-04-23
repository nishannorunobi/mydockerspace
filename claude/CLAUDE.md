# mydockerspace — Claude Context

This file is for Claude. It contains the full architecture, history of decisions, and rules for this project so Claude can pick up context in any session.

---

## What This Project Is

A generic, reusable Dockerized development workspace. The host machine has nothing installed except Docker. All tooling, users, and dependencies live inside the container. Multiple subprojects can live inside it — each manages its own deps.

The host and container each have their own git clone of the repo. They sync via GitHub push/pull — NOT via volume mount. The entire workspace root is volume-mounted into the container at the path defined by `CONTAINER_WORKDIR` in `workspace.conf`.

---

## Architecture

### Config files
- `dockerspace/workspace.conf` — Docker settings, package manager, git identity, SSH mode, package versions. Host + container scripts source this.
- `claude/claude.conf` — Claude-specific settings: `INSTALL_CLAUDE_CLI`, `COPY_CLAUDE_CONFIG`, `NODE_VERSION`. Sourced by `claude_cli.sh`.
- `project.conf` — Project-specific settings: `GIT_CLONE_URL`, `PROJECT_NAME`, project tool versions. Sourced by `functions.sh`.

### Shared function library: `dockerspace/functions.sh`
A pure library — defines functions only, never run directly. Sourced by container scripts.

Functions provided: `install_pkg`, `update_pkg_index`, `cleanup_pkg_cache`, `install_packages`, `setup_user`, `generate_ssh_key`, `copy_ssh_from_host`, `setup_git`, `setup_project`, `setup_workspace_group`.

### Per-environment container scripts
- `dockerspace/dev_container.sh` → creates and configures `devuser`
- `dockerspace/test_container.sh` → creates and configures `testuser`
- `dockerspace/prod_container.sh` → creates and configures `produser`

Each script sources `functions.sh` and `../claude/claude_cli.sh`, then calls the setup steps for its own user. `CONTAINER_TYPE` in `workspace.conf` controls which script `start.sh` runs.

Setup order per script: `install_packages` → `setup_user` → SSH → `setup_git` → `setup_workspace_group` → Claude CLI (if enabled) → `setup_project` (if `GIT_CLONE_URL` set).

### Workspace group: `dockerusergroup`
`$CONTAINER_WORKDIR` is root-owned by default. To give created users write access, all users are added to `dockerusergroup` and `$CONTAINER_WORKDIR` is set to `g+ws` with group ownership `dockerusergroup`. This runs at the end of each container script via `setup_workspace_group`.

---

## File Reference

| File | Where it runs | Purpose |
|---|---|---|
| `dockerspace/Dockerfile` | — | Base image + WORKDIR only — kept minimal |
| `dockerspace/workspace.conf` | Host + Container | All config: Docker settings, package manager, git identity, SSH mode, package versions |
| `dockerspace/functions.sh` | Container | Shared function library — do not run directly |
| `dockerspace/dev_container.sh` | Container | Full setup for devuser |
| `dockerspace/test_container.sh` | Container | Full setup for testuser |
| `dockerspace/prod_container.sh` | Container | Full setup for produser |
| `dockerspace/start.sh` | Host | Runs struct check, Docker check, builds image, starts container, runs selected container script |
| `dockerspace/stop.sh` | Host | Stops and removes container + image |
| `dockerspace/check_hostdocker.sh` | Host | Installs Docker if missing, starts daemon if stopped |
| `dockerspace/troubleshoot.sh` | Host | Creates and fixes ownership of `mountspace/` |
| `dockerspace/myworkspace_struct.sh` | Host | Creates any missing workspace directories (idempotent) |
| `claude/claude_cli.sh` | Host + Container | `install_node`, `install_claude_cli`, `setup_claude_config_host`, `setup_claude_config_container` — sourced by container scripts, run directly on host to launch Claude |
| `claude/start_claude.sh` | Container | Launches the claude binary |
| `claude/stop_claude.sh` | Container | Kills the claude process |

---

## Workspace Directory Structure

```
myworkspace/                    ← workspace root, mounted as $CONTAINER_WORKDIR in container
├── .gitignore
├── .vscode/settings.json
├── README.md
├── claude/                     ← Claude Code CLI
│   ├── CLAUDE.md
│   ├── claude_cli.sh
│   ├── start_claude.sh
│   ├── stop_claude.sh
│   ├── package.json
│   └── package-lock.json
├── dockerspace/                ← all host and container scripts
│   ├── Dockerfile
│   ├── workspace.conf
│   ├── functions.sh
│   ├── dev_container.sh
│   ├── test_container.sh
│   ├── prod_container.sh
│   ├── start.sh
│   ├── stop.sh
│   ├── check_hostdocker.sh
│   ├── troubleshoot.sh
│   └── myworkspace_struct.sh
├── $PROJECTSPACE_DIR/          ← gitignored, for user's subprojects
└── $MOUNTSPACE_DIR/            ← gitignored, for local files/media never committed
```

---

## Workflow

1. User edits `dockerspace/workspace.conf` (once, or when switching environments)
2. `bash dockerspace/start.sh` on host:
   - Runs `myworkspace_struct.sh` — creates any missing directories
   - Runs `check_hostdocker.sh` — installs Docker if missing, starts daemon if stopped
   - Builds Docker image from `dockerspace/` (Dockerfile is there)
   - Starts container, mounts workspace root as `$CONTAINER_WORKDIR`
   - Copies host `~/.ssh` to `/root/.ssh` inside container (if `COPY_SSH_FROM_HOST=true`)
   - Runs `troubleshoot.sh` — creates and chowns `$MOUNTSPACE_DIR/`
   - Runs `docker exec -it $CONTAINER_NAME bash $CONTAINER_WORKDIR/dockerspace/${CONTAINER_TYPE}_container.sh`
3. User enters container: `docker exec -it $CONTAINER_NAME bash`, then `su - <user>`
4. `bash dockerspace/stop.sh` on host — full clean (container + image removed)

---

## Base Image

The base image is **project-dependent** and will change based on what the subproject requires. It is not fixed. Current default is `ubuntu:24.04` but could be Debian, Red Hat, Alpine, or anything else. Always check the Dockerfile before making image-specific suggestions.

`PKG_MANAGER` in `workspace.conf` must match the base image (`apt` for Ubuntu/Debian, `yum`/`dnf` for Red Hat, `apk` for Alpine). `functions.sh` uses this to call the correct package manager commands.

---

## SSH Key Modes

Configured via `COPY_SSH_FROM_HOST` in `workspace.conf`:

- `true` — copies `/root/.ssh/id_ed25519` (placed there by `start.sh` from the host) into each user's `~/.ssh/`. Correct permissions are set (`600`/`644`). User does not need to re-add keys to GitHub.
- `false` — runs `ssh-keygen -t ed25519` for the user. Prints the public key at the end so the user can add it to GitHub/GitLab.

---

## Idempotency

All setup steps in all container scripts are safe to re-run multiple times:
- Packages: `apt-get install -y` skips already-installed packages
- User creation: checks `id $user` before `useradd`
- SSH key: checks if key file exists before generating or copying
- Git config: reads current config, skips if already set
- Group creation: checks `getent group` before `groupadd`
- Group membership: checks `id -nG` before `usermod`
- Directory creation: `mkdir -p` is always safe to re-run
- Project clone: checks for `.git` inside the target dir before cloning

---

## Rules

- Never mount only a subdirectory — the entire workspace root is mounted as `$CONTAINER_WORKDIR`
- Never auto-run container scripts from outside `start.sh` flow — they require root inside the container
- Never add project-specific tools to `functions.sh` or the `Dockerfile` — each subproject handles its own deps in its container script
- Never add subproject-specific ignores to root `.gitignore`
- Only add entries to `.gitignore` when the file/folder actually exists
- Keep the Dockerfile minimal — base image + WORKDIR only
- WORKDIR inside container is `$CONTAINER_WORKDIR` (set in `workspace.conf`, passed as Docker build arg)
- Do not assume a fixed base image — always check the Dockerfile before making image-specific suggestions
- `workspace.conf` is the single source of truth for all configuration — do not split config back into multiple files
- `functions.sh` is a library — never add execution logic to it, only function definitions
- All host-side scripts use `BASH_SOURCE[0]` (not `$0`) for path resolution so they work from any directory
