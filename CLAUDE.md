# mydockerspace — Claude Context

## Project Philosophy

- Nothing installed on the host except Docker
- All tooling lives inside the container
- Local machine and container each have their own git clone, synced via GitHub (NOT volume mount)
- Only `git-ignore-resources/` is volume-mounted between host and container

## Workflow (4 steps)

1. **Host:** `bash start.sh` — builds image, starts container (mounts git-ignore-resources/ only)
2. **Container:** `bash docker_env.sh` — installs OS-level deps
3. **Container:** work inside the container (subproject-specific setup)
4. **Host:** `bash stop.sh` — docker stop + rm + rmi (full clean)

## Key Files

- `docker_config.sh` — host-side env vars (IMAGE_NAME, CONTAINER_NAME, paths), sourced by start/stop
- `docker_env.sh` — runs INSIDE container, installs OS deps
- `start.sh` — builds image + runs container, mounts git-ignore-resources/ only
- `stop.sh` — docker stop + docker rm + docker rmi

## Project Nature

- This is a **generic multi-project workspace** — many different subprojects will live inside it
- Do not assume any specific tool (e.g. ffmpeg) is relevant unless the subproject requires it
- `docker_env.sh` installs only generic dev essentials (curl, wget, git, vim, unzip, build-essential)
- Each subproject manages its own deps and `.gitignore`

## VS Code Preferences

- Theme: `Visual Studio Dark`
- Tab size: 4
- Format on save: true
- Default terminal: bash
- `git-ignore-resources/` is hidden from the file explorer

## Rules

- Never mount the entire project directory — only `git-ignore-resources/`
- Never auto-run `docker_env.sh` from `start.sh`
- Never add project-specific tools to the Dockerfile or root `docker_env.sh` — subprojects handle their own deps
- Never add subproject-specific ignores to root `.gitignore`
- Only add entries to `.gitignore` when the file/folder actually exists
- Base image is `debian:bookworm-slim` — keep it minimal, no Python or extras in Dockerfile
- WORKDIR inside container is `/mydockerspace`
