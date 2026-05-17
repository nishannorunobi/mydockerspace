import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/workspace", tags=["workspace"])

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROJECTSPACE   = WORKSPACE_ROOT / "projectspace"
PORT_FORWARDS_FILE = (
    WORKSPACE_ROOT / "agents/docker-manager-agent/docker_agent/memory/port_forwards.json"
)

_EXCLUDE = {"temp", "__pycache__", ".git"}

_procs:  dict[str, object]       = {}
_output: dict[str, list[str]]    = {}


def _find_script(project: Path, names: list[str]) -> str | None:
    for d in [project / "dockerspace" / "host_scripts", project]:
        for name in names:
            p = d / name
            if p.exists():
                return str(p)
    return None


def _find_log_file(project: Path) -> str | None:
    """Return the first readable log file found in common locations."""
    candidates = [
        project / "logs" / "app.log",
        project / "log" / "app.log",
        project / "dockerspace" / "host_scripts" / "logs.sh",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _container_running(project_name: str) -> bool:
    """Return True if a Docker container whose name contains project_name is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={project_name}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _reader(name: str, proc):
    for line in proc.stdout:
        _output[name].append(line.rstrip("\n"))
    proc.wait()


def _socat_pid_for_port(port: int) -> int | None:
    """Return PID of a process listening on the given TCP port, or None."""
    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=5,
        )
        m = re.search(r'pid=(\d+)', result.stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _release_project_ports(project_name: str, log: list[str]) -> None:
    """
    Force-kill any processes holding ports tracked for this project
    and remove those entries from port_forwards.json.
    """
    if not PORT_FORWARDS_FILE.exists():
        return
    try:
        pf: dict = json.loads(PORT_FORWARDS_FILE.read_text())
    except Exception:
        return

    ports_to_free = [
        port_str for port_str, info in pf.items()
        if project_name in info.get("container", "")
    ]

    if not ports_to_free:
        return

    changed = False
    for port_str in ports_to_free:
        port = int(port_str)
        pid  = _socat_pid_for_port(port)
        if pid:
            try:
                os.kill(pid, 9)  # SIGKILL
                log.append(f"[pre-start] killed PID {pid} holding port {port}")
            except ProcessLookupError:
                pass
        pf.pop(port_str, None)
        changed = True

    if changed:
        PORT_FORWARDS_FILE.write_text(json.dumps(pf, indent=2))
        log.append("[pre-start] port_forwards.json cleaned")


@router.get("/projects")
def list_projects():
    if not PROJECTSPACE.exists():
        return {"projects": []}

    projects = []
    for entry in sorted(PROJECTSPACE.iterdir()):
        if not entry.is_dir() or entry.name in _EXCLUDE:
            continue
        start   = _find_script(entry, ["start.sh", "start_docker.sh"])
        stop    = _find_script(entry, ["stop.sh",  "stop_docker.sh"])
        health  = _find_script(entry, ["health.sh"])
        logs    = _find_script(entry, ["logs.sh"])
        compose = (entry / "dockerspace" / "host_scripts" / "docker-compose.yml").exists() or \
                  (entry / "docker-compose.yml").exists()
        running = _container_running(entry.name)
        projects.append({
            "name":          entry.name,
            "start_script":  start,
            "stop_script":   stop,
            "health_script": health,
            "logs_script":   logs,
            "has_compose":   compose,
            "running":       running,
        })
    return {"projects": projects}


@router.post("/projects/{name}/start")
def start_project(name: str):
    project = PROJECTSPACE / name
    if not project.exists():
        return JSONResponse({"error": f"Project '{name}' not found"}, status_code=404)

    script = _find_script(project, ["start.sh", "start_docker.sh"])
    if not script:
        return JSONResponse({"error": "No start script found for this project"}, status_code=400)

    # Terminate any previous tracked proc
    old = _procs.get(name)
    if old and old.poll() is None:
        old.terminate()

    # Pre-start log visible to the user immediately
    pre_log: list[str] = []
    _release_project_ports(name, pre_log)

    _output[name] = list(pre_log)

    proc = subprocess.Popen(
        ["bash", script],
        cwd=str(Path(script).parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    _procs[name] = proc

    t = threading.Thread(target=_reader, args=(name, proc), daemon=True)
    t.start()

    return {"ok": True, "script": script}


@router.post("/projects/{name}/stop")
def stop_project(name: str):
    project = PROJECTSPACE / name
    if not project.exists():
        return JSONResponse({"error": f"Project '{name}' not found"}, status_code=404)

    script = _find_script(project, ["stop.sh", "stop_docker.sh"])
    if script:
        try:
            result = subprocess.run(
                ["bash", script],
                cwd=str(Path(script).parent),
                capture_output=True, text=True, timeout=60,
            )
            output = (result.stdout + result.stderr).strip()
            return {"ok": True, "output": output or "Stop script completed"}
        except subprocess.TimeoutExpired:
            return JSONResponse({"error": "Stop script timed out"}, status_code=500)

    proc = _procs.get(name)
    if proc and proc.poll() is None:
        proc.terminate()
        return {"ok": True, "output": "Process terminated"}

    return {"ok": False, "error": "No stop script and no running process found"}


@router.get("/projects/{name}/log")
def stream_log(name: str):
    if name not in _output:
        return JSONResponse({"error": "No log for this project"}, status_code=404)

    output = _output[name]
    proc   = _procs.get(name)

    def generate():
        sent = 0
        yield ": ping\n\n"
        while True:
            current_len = len(output)
            for i in range(sent, current_len):
                yield f"data: {output[i]}\n\n"
            sent = current_len

            if proc is not None and proc.poll() is not None and sent >= len(output):
                rc = proc.returncode
                yield f"data: \n\n"
                yield f"data: [Process exited — code {rc}]\n\n"
                yield "data: __done__\n\n"
                return

            time.sleep(0.15)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/projects/{name}/health")
def health_project(name: str):
    project = PROJECTSPACE / name
    if not project.exists():
        return JSONResponse({"error": f"Project '{name}' not found"}, status_code=404)

    script = _find_script(project, ["health.sh"])
    if not script:
        return {"ok": False, "output": "No health.sh found for this project"}

    try:
        result = subprocess.run(
            ["bash", script],
            cwd=str(Path(script).parent),
            capture_output=True, text=True, timeout=15,
        )
        output = (result.stdout + result.stderr).strip()
        return {"ok": result.returncode == 0, "output": output or "(no output)"}
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "Health check timed out"}, status_code=500)


@router.get("/projects/{name}/docker-logs")
def stream_docker_logs(name: str):
    project = PROJECTSPACE / name
    if not project.exists():
        return JSONResponse({"error": f"Project '{name}' not found"}, status_code=404)

    # Prefer logs.sh if it exists; otherwise fall back to docker compose logs
    logs_script = _find_script(project, ["logs.sh"])
    compose_file = None
    for candidate in [
        project / "dockerspace" / "host_scripts" / "docker-compose.yml",
        project / "docker-compose.yml",
    ]:
        if candidate.exists():
            compose_file = candidate
            break

    if logs_script:
        cmd = ["bash", logs_script]
        cwd = str(Path(logs_script).parent)
    elif compose_file:
        cmd = ["docker", "compose", "-f", str(compose_file), "logs", "--tail=80", "--no-log-prefix"]
        cwd = str(compose_file.parent)
    else:
        return JSONResponse({"error": "No logs.sh or docker-compose.yml found"}, status_code=400)

    _output[name] = []
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    _procs[name] = proc
    t = threading.Thread(target=_reader, args=(name, proc), daemon=True)
    t.start()

    output = _output[name]

    def generate():
        sent = 0
        yield ": ping\n\n"
        while True:
            current_len = len(output)
            for i in range(sent, current_len):
                yield f"data: {output[i]}\n\n"
            sent = current_len
            if proc.poll() is not None and sent >= len(output):
                yield "data: \n\n"
                yield f"data: [Logs complete — exit {proc.returncode}]\n\n"
                yield "data: __done__\n\n"
                return
            time.sleep(0.15)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
