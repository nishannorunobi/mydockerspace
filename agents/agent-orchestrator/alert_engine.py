"""
Alert Engine — polls agent statuses, detects state changes, and broadcasts
alert events to all connected SSE subscribers via the asyncio event loop.

Thread-safety: _subscribers is only touched from the event loop.
The background AlertPoller uses loop.call_soon_threadsafe() to bridge threads.
"""
import asyncio
import os
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agent_registry import AGENT_SPECS, SPEC_BY_ID, refresh_all

POLL_INTERVAL = 15  # seconds between status polls

_loop: Optional[asyncio.AbstractEventLoop] = None
_subscribers: List[asyncio.Queue] = []   # only accessed from event loop


def init(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


# ── Pub / sub ──────────────────────────────────────────────────────────────────

def subscribe() -> asyncio.Queue:
    """Register an SSE client. Called from the event loop."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue):
    """Deregister an SSE client. Called from the event loop."""
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def _broadcast_sync(event: dict):
    """Push event to every subscriber queue. Must run in event loop."""
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)


def broadcast(event: dict):
    """Thread-safe broadcast from any thread."""
    if _loop and not _loop.is_closed():
        _loop.call_soon_threadsafe(_broadcast_sync, event)


# ── Workspace change passthrough ───────────────────────────────────────────────

def on_workspace_change(ts: str, added: list, removed: list):
    """Called by WorkspaceMonitor (background thread)."""
    broadcast({"type": "workspace_change", "ts": ts, "added": added, "removed": removed})


# ── Alert construction ─────────────────────────────────────────────────────────

_ALERT_RULES = {
    # (new_status, prev_status) → (alert_type, severity, message_template)
    ("stopped",     "running"):   ("agent_down",      "critical", "{name} went offline"),
    ("unavailable", "running"):   ("agent_down",      "critical", "{name} is unavailable"),
    ("running",     "stopped"):   ("agent_recovered", "info",     "{name} is back online"),
    ("running",     "unavailable"): ("agent_recovered", "info",   "{name} is back online"),
}


def _make_alert(ev: dict) -> Optional[dict]:
    key = (ev["status"], ev["prev_status"])
    rule = _ALERT_RULES.get(key)
    if not rule:
        return None
    alert_type, severity, tmpl = rule
    return {
        "type":       "alert",
        "id":         str(uuid.uuid4()),
        "alert_type": alert_type,
        "severity":   severity,
        "agent_id":   ev["agent_id"],
        "agent_name": ev["agent_name"],
        "message":    tmpl.format(name=ev["agent_name"]),
        "ts":         datetime.now().isoformat(),
    }


# ── Auto-restart ───────────────────────────────────────────────────────────────

_restart_cooldown: dict = {}   # agent_id → last restart timestamp
_RESTART_COOLDOWN_S = 30       # don't restart more than once per 30s


def _auto_restart(agent_id: str):
    """Spawn start_script for an agent in a background thread."""
    now = time.time()
    last = _restart_cooldown.get(agent_id, 0)
    if now - last < _RESTART_COOLDOWN_S:
        return
    _restart_cooldown[agent_id] = now

    spec = SPEC_BY_ID.get(agent_id)
    if not spec or not spec.home or not spec.start_script:
        return

    script_path = Path(spec.home) / spec.start_script
    if not script_path.exists():
        return

    def _run():
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".log", mode="w")
        subprocess.Popen(
            ["bash", str(script_path)],
            cwd=spec.home,
            stdin=subprocess.DEVNULL,
            stdout=tmp,
            stderr=tmp,
            start_new_session=True,
            env=os.environ.copy(),
        )
        tmp.close()

    broadcast({
        "type": "alert", "id": str(uuid.uuid4()),
        "alert_type": "auto_restart", "severity": "info",
        "agent_id": agent_id, "agent_name": spec.name,
        "message": f"{spec.name} stopped — auto-restarting…",
        "ts": datetime.now().isoformat(),
    })
    threading.Thread(target=_run, daemon=True).start()


# ── Poller thread ──────────────────────────────────────────────────────────────

class AlertPoller(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop = threading.Event()
        refresh_all()   # baseline — don't alert on initial state

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.wait(POLL_INTERVAL):
            try:
                for ev in refresh_all():
                    # Status change event (for UI refresh)
                    broadcast(ev)
                    # Alert event (triggers sound + banner)
                    alert = _make_alert(ev)
                    if alert:
                        broadcast(alert)
                    # Auto-restart if configured
                    if ev["status"] == "stopped":
                        spec = SPEC_BY_ID.get(ev["agent_id"])
                        if spec and spec.auto_restart:
                            _auto_restart(ev["agent_id"])
            except Exception:
                pass
