"""
Alert Engine — polls agent statuses, detects state changes, and broadcasts
alert events to all connected SSE subscribers via the asyncio event loop.

Thread-safety: _subscribers is only touched from the event loop.
The background AlertPoller uses loop.call_soon_threadsafe() to bridge threads.
"""
import asyncio
import threading
import uuid
from datetime import datetime
from typing import List, Optional

from agent_registry import AGENT_SPECS, refresh_all

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
            except Exception:
                pass
