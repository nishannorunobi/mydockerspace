# Workspace Context

> **FOR CLAUDE:** Read this file at the start of every conversation. Update it after every prompt where something changes — scripts, config, architecture, decisions, or rules. No exceptions.

## Project: myworkspace
A Dockerized workspace that acts as a container dashboard to manage all project containers and Docker UI.

---

## Architecture

### Workspace Role
- `myworkspace` is the **dashboard/orchestrator** — manages all project containers and Docker UI
- Each project (API-Gateway, ums) runs in its **own independent container**
- Docker UI (Portainer) manages all containers from the browser

### Directory Structure
```
myworkspace/
  dockerspace/          ← all workspace-level docker scripts
  projectspace/         ← cloned project repos (gitignored)
    API-Gateway/
      dockerspace/      ← independent container scripts for APISIX project
    ums/
      dockerspace/      ← independent container scripts for UMS project
  mountspace/           ← local files, never committed (gitignored)
  context.md            ← this file
```

---

## Configuration Files

### workspace.conf (OS/infrastructure level)
- `IMAGE_NAME` → derived from `${PROJECT_NAME}-image`
- `IMAGE_VERSION` → current: `1.4`
- `CONTAINER_NAME` → derived from `${PROJECT_NAME}-container`
- `BASE_IMAGE` → current: `postgres:16`
- `PKG_MANAGER` → current: `apt`
- Package names and versions (configurable per distro)

### project.conf (project-specific)
- `PROJECT_NAME` → sourced FIRST so workspace.conf can reference it for image/container naming
- `GIT_USER_NAME`, `GIT_USER_EMAIL`
- `GIT_CLONE_URL` → repo to clone into projectspace/
- Source order: **project.conf → workspace.conf** (project.conf must always come first)

---

## Scripts — Workspace Level (dockerspace/)

| Script | Purpose |
|---|---|
| `start_project_container.sh` | Build image + start workspace container |
| `stop_project_container.sh` | Stop workspace container |
| `start_system_docker.sh` | Start Docker daemon + socket |
| `stop_system_docker.sh` | Stop all containers + Docker daemon + socket |
| `stop_the_world.sh` | stop_system_docker → shutdown PC |
| `restart_the_world.sh` | stop_system_docker → reboot PC |
| `start_docker_ui.sh` | Start Portainer CE on port 9000 |
| `stop_docker_ui.sh` | Stop Portainer |
| `check_and_install_docker.sh` | Check/install Docker, report status (manual use only) |
| `os_explore.sh` | Open OS filesystem in VSCode as root |
| `docker_backup.sh` | Snapshot container state to versioned image |
| `docker_clean.sh` | Clean unused Docker resources |
| `docker_dashboard.sh` | Dashboard overview |
| `functions.sh` | Shared library (install_packages, setup_user, etc.) |
| `dev_container.sh` | Setup script run inside workspace container |

> `prod_container.sh` and `test_container.sh` removed — add back when needed.

## Scripts — Per-Project Level (project/dockerspace/)

Each project (API-Gateway, ums) has its own independent:
- `start.sh` / `stop.sh`
- `workspace.conf` (IMAGE_NAME, CONTAINER_NAME, BASE_IMAGE, PKG_MANAGER)
- `project.conf` (git identity, project tools)
- `Dockerfile`
- `functions.sh`
- `setup.sh` (runs inside container on first start)

---

## Projects

### API-Gateway (APISIX)
- Repo: `git@github.com:nishannorunobi/myapigw.git`
- Purpose: APISIX API gateway for Node.js backend service
- Container: `myapigw-container`, Image: `myapigw-image`

### UMS (User Management System)
- Repo: `git@github.com:nishannorunobi/ums.git`
- Stack: Java 21, Spring Boot 3, Maven
- Container: `ums-app`, Image: `ums-image`
- Port: 8080, Network: `ums-network`

---

## Key Decisions & Rules

- **OS changes** → update `workspace.conf`: `BASE_IMAGE`, `PKG_MANAGER`, package names
- **Project name** → set in `project.conf`, drives image/container naming in `workspace.conf`
- **Source order** → always `project.conf` first, then `workspace.conf`
- **Docker auto-start on boot disabled** → `sudo systemctl disable docker.service docker.socket`
- **check_and_install_docker.sh** is standalone — does NOT auto-start daemon
- **start_project_container.sh** does NOT auto-start Docker — fails naturally if daemon is down
- **Claude permissions** → configured manually in `~/.claude/settings.json` (outside workspace, user-controlled)
- **Portainer** runs on `http://localhost:9000`
- **No Claude references** in any shell scripts — claude/ dir is gitignored
---

## OS & Environment
- OS: Linux (Ubuntu/XFCE desktop)
- Docker base image: `postgres:16`
- Package manager inside containers: `apt`
- Guake terminal autostart: `~/.config/autostart/guake.desktop`
