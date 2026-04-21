# mydockerspace

A Dockerized development workspace. Nothing is installed on the host machine except Docker — all tooling runs inside the container.

## Philosophy

- Local machine and Docker container each have their own git clone
- They sync via **git push/pull through GitHub** — not via volume mount
- Only `git-ignore-resources/` is volume-mounted (for sharing local files/media)

## Workflow

### 1. Start the container (run on host)
```bash
bash start.sh
```
Builds the Docker image and starts the container with `git-ignore-resources/` mounted.

### 2. Set up environment (run inside container)
```bash
bash docker_env.sh
```
Installs OS-level dependencies (ffmpeg, etc.) inside the container.

### 3. Stop and clean up (run on host)
```bash
bash stop.sh
```
Stops the container and removes the container + image (full clean).

## File Reference

| File | Where it runs | Purpose |
|------|--------------|---------|
| `Dockerfile` | — | Base image definition (python:3.10-slim + git + curl) |
| `docker_config.sh` | Host | Defines IMAGE_NAME, CONTAINER_NAME, paths |
| `start.sh` | Host | Builds image + starts container |
| `stop.sh` | Host | Stops + removes container and image |
| `docker_env.sh` | Container | Installs OS deps (ffmpeg, etc.) |

## Notes

- `git-ignore-resources/` is gitignored — use it for media files or local assets
- `.vscode/` is gitignored — VS Code settings are local only
- Each subproject manages its own `.gitignore`
