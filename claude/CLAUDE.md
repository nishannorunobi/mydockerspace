# mydockerspace — Claude Context

This file is for Claude. It contains the full architecture, history of decisions, and rules for this project so Claude can pick up context in any session.

---

## What This Project Is

A generic, reusable Dockerized development workspace. The host machine has nothing installed except Docker. All tooling, users, and dependencies live inside the container. Multiple subprojects can live inside it — each manages its own deps.

The host and container each have their own git clone of the repo. They sync via GitHub push/pull — NOT via volume mount. Only `git-ignore-resources/` is volume-mounted (for local files/media that should never be committed).

---

## Architecture

### Single config file: `workspace.conf`
Originally there were two separate config files:
- `docker_config.sh` — host-side Docker settings (image name, container name, container type)
- `library_versions.env` — container-side settings (package manager, package versions, git identity, SSH mode)

These were merged into a single `workspace.conf` because both are just bash variable files and there was no practical reason to split them. Both host scripts and container scripts source the same file. Sections are clearly separated with comments.

### Shared function library: `functions.sh`
Originally called `docker_env.sh`, renamed to `functions.sh` to make its role clear. It is a pure library — it defines functions only and must never be run directly. It is sourced by the container scripts.

Functions provided: `install_pkg`, `update_pkg_index`, `cleanup_pkg_cache`, `install_packages`, `setup_user`, `setup_ssh`, `setup_git`, `setup_workspace_group`.

### Per-environment container scripts
Instead of one `docker_env.sh` that set up all users, the setup is split into three dedicated scripts, one per environment:
- `dev_container.sh` → creates and configures `devuser`
- `test_container.sh` → creates and configures `testuser`
- `prod_container.sh` → creates and configures `produser`

Each script sources `functions.sh` and calls the setup steps for its own user. `CONTAINER_TYPE` in `workspace.conf` controls which script `start.sh` runs.

### Workspace group: `dockerusergroup`
`/mydockerspace` is root-owned by default. To give created users write access, all users are added to `dockerusergroup` and `/mydockerspace` is set to `g+ws` with group ownership `dockerusergroup`. This runs at the end of each container script via `setup_workspace_group`.

---

## File Reference

| File | Where it runs | Purpose |
|---|---|---|
| `Dockerfile` | — | Base image + WORKDIR only — kept minimal |
| `workspace.conf` | Host + Container | All config: Docker settings, package manager, git identity, SSH mode, package versions |
| `functions.sh` | Container | Shared function library — do not run directly |
| `dev_container.sh` | Container | Full setup for devuser |
| `test_container.sh` | Container | Full setup for testuser |
| `prod_container.sh` | Container | Full setup for produser |
| `claude/claude_cli.sh` | Container | Claude Code CLI setup (install_node, install_claude_cli) — sourced by container scripts |
| `start.sh` | Host | Builds image, starts container, runs selected container script via `docker exec -it` |
| `stop.sh` | Host | Stops and removes container + image |
| `permission.sh` | Host | Fixes ownership of `git-ignore-resources/` after container start |

---

## Workflow

1. User edits `workspace.conf` (once, or when switching environments)
2. `bash start.sh` on host:
   - Builds Docker image
   - Starts container (mounts only `git-ignore-resources/`)
   - Copies host `~/.ssh` to `/root/.ssh` inside container
   - Copies `.vscode/settings.json` into container
   - Runs `docker exec -it $CONTAINER_NAME bash /mydockerspace/${CONTAINER_TYPE}_container.sh`
   - Runs `permission.sh` to fix ownership of `git-ignore-resources/`
3. User enters container: `docker exec -it mydockerspace-container bash`, then `su - <user>`
4. `bash stop.sh` on host — full clean (container + image removed)

---

## Base Image

The base image is **project-dependent** and will change based on what the subproject requires. It is not fixed. Current default is `ubuntu:24.04` but could be Debian, Red Hat, Alpine, or anything else. Always check the Dockerfile before making image-specific suggestions.

`PKG_MANAGER` in `workspace.conf` must match the base image (`apt` for Ubuntu/Debian, `yum`/`dnf` for Red Hat, `apk` for Alpine). `functions.sh` uses this to call the correct package manager commands.

---

## SSH Key Modes

Configured via `SSH_KEY_MODE` in `workspace.conf`:

- `copy_from_host` — copies `/root/.ssh/id_ed25519` (placed there by `start.sh` from the host) into each user's `~/.ssh/`. Correct permissions are set (`600`/`644`). User does not need to re-add keys to GitHub.
- `generate` — runs `ssh-keygen -t ed25519` for the user. Prints the public key at the end so the user can add it to GitHub/GitLab. Use this when starting fresh or when the container needs its own identity.

---

## Idempotency

All setup steps in all container scripts are safe to re-run multiple times:
- Packages: `apt-get install -y` skips already-installed packages
- User creation: checks `id $user` before `useradd`
- SSH key: checks if key file exists before generating or copying
- Git config: reads current config, skips if already set
- Group creation: checks `getent group` before `groupadd`
- Group membership: checks `id -nG` before `usermod`

---

## Rules

- Never mount the entire project directory — only `git-ignore-resources/`
- Never auto-run container scripts from outside `start.sh` flow — they require root inside the container
- Never add project-specific tools to `functions.sh` or the `Dockerfile` — each subproject handles its own deps in its container script
- Never add subproject-specific ignores to root `.gitignore`
- Only add entries to `.gitignore` when the file/folder actually exists
- Keep the Dockerfile minimal — base image + WORKDIR only
- WORKDIR inside container is `/mydockerspace`
- Do not assume a fixed base image — always check the Dockerfile before making image-specific suggestions
- `workspace.conf` is the single source of truth for all configuration — do not split config back into multiple files
- `functions.sh` is a library — never add execution logic to it, only function definitions
