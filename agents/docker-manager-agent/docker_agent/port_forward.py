"""
Port forwarding manager — uses socat to expose container ports on the host.

When an agent inside a container starts a service (e.g. pgweb on 8085),
it calls POST /api/port-forward and this module starts a socat tunnel so
the host port becomes reachable at http://localhost:{host_port}.

Forwards are persisted to memory/port_forwards.json and restored on startup.
"""
import json
import subprocess
import threading
from pathlib import Path

_LOCK        = threading.Lock()
_PROCS: dict[int, subprocess.Popen] = {}   # host_port → socat process
_STATE_FILE  = Path(__file__).parent / "memory" / "port_forwards.json"


def _save():
    _STATE_FILE.parent.mkdir(exist_ok=True)
    state = {str(hp): info for hp, info in _active().items()}
    _STATE_FILE.write_text(json.dumps(state, indent=2))


def _active() -> dict:
    """Return {host_port: {"container": ..., "container_port": ..., "host_port": ...}} for live procs."""
    return {k: v for k, v in _META.items() if k in _PROCS and _PROCS[k].poll() is None}


_META: dict[int, dict] = {}   # host_port → metadata


def start(host_port: int, container_ip: str, container_port: int,
          container: str = "", label: str = "") -> dict:
    """Start (or replace) a socat tunnel. Returns status dict."""
    with _LOCK:
        _stop_port(host_port)
        try:
            proc = subprocess.Popen(
                ["socat", f"TCP-LISTEN:{host_port},fork,reuseaddr",
                 f"TCP:{container_ip}:{container_port}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            _PROCS[host_port] = proc
            _META[host_port]  = {
                "host_port":      host_port,
                "container":      container,
                "container_ip":   container_ip,
                "container_port": container_port,
                "label":          label,
            }
            _save()
            return {"ok": True, "host_port": host_port,
                    "url": f"http://localhost:{host_port}", "pid": proc.pid}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def stop(host_port: int) -> dict:
    with _LOCK:
        stopped = _stop_port(host_port)
        _save()
    return {"ok": stopped, "host_port": host_port}


def _stop_port(host_port: int) -> bool:
    proc = _PROCS.pop(host_port, None)
    _META.pop(host_port, None)
    if proc and proc.poll() is None:
        proc.terminate()
        return True
    # also kill any stray socat on that port
    subprocess.run(["pkill", "-f", f"socat.*TCP-LISTEN:{host_port}"],
                   capture_output=True)
    return bool(proc)


def list_forwards() -> list:
    with _LOCK:
        result = []
        for hp, meta in list(_META.items()):
            proc = _PROCS.get(hp)
            alive = proc is not None and proc.poll() is None
            result.append({**meta, "active": alive})
        return result


def restore_from_disk():
    """Called on startup — re-launch socat for any saved forwards."""
    if not _STATE_FILE.exists():
        return
    try:
        saved = json.loads(_STATE_FILE.read_text())
        for _hp, info in saved.items():
            start(
                host_port=info["host_port"],
                container_ip=info["container_ip"],
                container_port=info["container_port"],
                container=info.get("container", ""),
                label=info.get("label", ""),
            )
    except Exception:
        pass
