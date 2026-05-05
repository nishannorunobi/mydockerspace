"""
Docker Monitor — polls Docker every INTERVAL seconds.
- Detects containers that transition from running → stopped
- Auto-restarts them and logs the event + result to the database
- Auto-starts the db-agent inside mypostgresql_db-container when it comes up
- Writes docker_status.json for the agent-orchestrator to consume
"""
import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import database as db

DB_CONTAINER   = "mypostgresql_db-container"
DB_AGENT_START = "/mypostgresql_db/db-agent/start.sh"
DB_AGENT_PORT  = 8890


def _start_db_agent_in_container():
    """Launch the db-agent HTTP server inside the DB container (non-blocking)."""
    try:
        subprocess.Popen(
            ["docker", "exec", "-d", DB_CONTAINER,
             "bash", "-c",
             f"cd /mypostgresql_db/db-agent && nohup bash start.sh > memory/server.log 2>&1 &"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _db_agent_running() -> bool:
    """Return True if the db-agent is already listening inside the DB container."""
    try:
        r = subprocess.run(
            ["docker", "exec", DB_CONTAINER,
             "curl", "-sf", f"http://localhost:{DB_AGENT_PORT}/health"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False

MEMORY_DIR  = Path(__file__).resolve().parent / "memory"
STATUS_FILE = MEMORY_DIR / "docker_status.json"


# ── Docker CLI helpers ────────────────────────────────────────────────────────

def _run(cmd: list, timeout: int = 15) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, f"timed out after {timeout}s"
    except FileNotFoundError:
        return 1, "docker CLI not found"
    except Exception as e:
        return 1, str(e)


def list_containers(all_containers: bool = True) -> list[dict]:
    """Returns all containers with id, name, status, image, running_for."""
    fmt = "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.RunningFor}}"
    args = ["docker", "ps", "--format", fmt]
    if all_containers:
        args.append("-a")
    rc, out = _run(args)
    if rc != 0 or not out:
        return []
    result = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            result.append({
                "id":          parts[0],
                "name":        parts[1],
                "status":      parts[2],
                "image":       parts[3],
                "running_for": parts[4] if len(parts) > 4 else "",
            })
    return result


def get_stats() -> list[dict]:
    """Returns CPU + memory stats for all running containers (non-blocking)."""
    rc, out = _run(
        ["docker", "stats", "--no-stream", "--format",
         "{{.ID}}\t{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"],
        timeout=25,
    )
    if rc != 0 or not out:
        return []
    result = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            result.append({
                "id":      parts[0],
                "name":    parts[1],
                "cpu":     parts[2],
                "memory":  parts[3],
                "mem_pct": parts[4] if len(parts) > 4 else "",
            })
    return result


def restart_container(name_or_id: str) -> tuple[bool, str]:
    rc, out = _run(["docker", "restart", name_or_id], timeout=45)
    return rc == 0, out or ("restarted" if rc == 0 else "failed")


def start_container(name_or_id: str) -> tuple[bool, str]:
    rc, out = _run(["docker", "start", name_or_id], timeout=30)
    return rc == 0, out or ("started" if rc == 0 else "failed")


def stop_container(name_or_id: str) -> tuple[bool, str]:
    rc, out = _run(["docker", "stop", name_or_id], timeout=30)
    return rc == 0, out or ("stopped" if rc == 0 else "failed")


def get_logs(name_or_id: str, lines: int = 100) -> str:
    rc, out = _run(["docker", "logs", "--tail", str(lines), name_or_id], timeout=10)
    return out[-6000:] if out else "(no output)"


# ── Status snapshot ───────────────────────────────────────────────────────────

def write_status():
    """Write docker_status.json — machine-readable snapshot for agent-orchestrator."""
    containers = list_containers(all_containers=True)
    stats_map  = {s["name"]: s for s in get_stats()}
    for c in containers:
        s = stats_map.get(c["name"], {})
        c["cpu"]    = s.get("cpu", "—")
        c["memory"] = s.get("memory", "—")

    MEMORY_DIR.mkdir(exist_ok=True)
    STATUS_FILE.write_text(json.dumps({
        "last_updated":     datetime.now().isoformat(timespec="seconds"),
        "total_containers": len(containers),
        "running":          sum(1 for c in containers if "Up" in c.get("status", "")),
        "stopped":          sum(1 for c in containers if "Up" not in c.get("status", "")),
        "containers":       containers,
        "recent_events":    db.get_events(10),
    }, indent=2))


# ── Monitor thread ────────────────────────────────────────────────────────────

class DockerMonitor(threading.Thread):
    INTERVAL = 15  # seconds between polls

    def __init__(self, on_event: Optional[Callable[[str, str, str], None]] = None):
        super().__init__(daemon=True)
        self._stop    = threading.Event()
        self._on_event = on_event        # callback(container_name, event_type, detail)
        self._known: dict[str, str] = {} # name → last known status string

    def stop(self):
        self._stop.set()

    def run(self):
        db.init()
        MEMORY_DIR.mkdir(exist_ok=True)
        # Seed initial state so first poll doesn't false-positive
        for c in list_containers():
            self._known[c["name"]] = c["status"]
        write_status()
        while not self._stop.wait(self.INTERVAL):
            self._poll()

    def _poll(self):
        current = {c["name"]: c for c in list_containers(all_containers=True)}

        for name, c in current.items():
            prev = self._known.get(name, "")
            now  = c["status"]

            if name not in self._known:
                # Newly appeared container
                db.log_event(c["id"], name, "detected", now)

            elif "Up" in prev and "Up" not in now:
                # Was running, now stopped → auto-restart
                db.log_event(c["id"], name, "stopped", f"was: {prev!r}")
                ok, msg = restart_container(c["id"])
                event   = "restarted" if ok else "restart_failed"
                db.log_event(c["id"], name, event, msg)
                if self._on_event:
                    self._on_event(name, event, msg)

            elif "Up" not in prev and "Up" in now and name == DB_CONTAINER:
                # DB container just came up → auto-start db-agent inside it
                db.log_event(c["id"], name, "db_agent_autostart", "container came up")
                threading.Thread(target=_start_db_agent_in_container, daemon=True).start()

        self._known = {name: c["status"] for name, c in current.items()}

        # Persist snapshots + refresh status file
        stats_map = {s["name"]: s for s in get_stats()}
        for c in current.values():
            s = stats_map.get(c["name"], {})
            db.log_snapshot(c["id"], c["name"], c["status"], c["image"],
                            s.get("cpu", ""), s.get("memory", ""))
        write_status()
