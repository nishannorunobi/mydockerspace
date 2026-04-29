"""
Task Executor — reads tasks.json, runs tasks via agent connectors.

Lifecycle
---------
- on_start tasks   : dispatched once at server startup
- interval:<N>     : dispatched every N seconds in background
- manual           : only dispatched when POST /api/tasks/{id}/run is called

All task state (status, last result, last run time) is kept in memory.
Edit tasks.json to add, remove, or reschedule tasks — then restart the server.
"""
import asyncio
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import agent_registry as registry

_TASKS_JSON = Path(__file__).resolve().parent.parent / "tasks.json"

# ── In-memory state per task ───────────────────────────────────────────────────
# { task_id: { ...definition, status, last_run, last_result, last_error } }
_state: dict[str, dict] = {}
_lock  = threading.Lock()


# ── Load config ────────────────────────────────────────────────────────────────

def load() -> list[dict]:
    """Read tasks.json and return the tasks list. Raises on bad JSON."""
    data = json.loads(_TASKS_JSON.read_text())
    return [t for t in data.get("tasks", []) if t.get("enabled", True)]


def init():
    """Populate in-memory state from tasks.json. Call once at startup."""
    tasks = load()
    with _lock:
        for t in tasks:
            _state[t["id"]] = {
                **t,
                "status":      "idle",
                "last_run":    None,
                "last_result": None,
                "last_error":  None,
            }


def get_all() -> list[dict]:
    with _lock:
        return [dict(v) for v in _state.values()]


def get(task_id: str) -> Optional[dict]:
    with _lock:
        t = _state.get(task_id)
        return dict(t) if t else None


# ── Dispatch ───────────────────────────────────────────────────────────────────

def _dispatch_sync(task: dict) -> str:
    """Dispatch a task to its agent. Runs in a thread — uses a fresh event loop."""
    agent_id  = task["agent_id"]
    spec      = registry.SPEC_BY_ID.get(agent_id)
    if not spec:
        raise ValueError(f"Unknown agent: '{agent_id}'")
    connector = registry.make_connector(spec)
    if not connector:
        raise ValueError(f"Agent '{agent_id}' has no connector configured")
    if not connector.is_available():
        raise ValueError(f"Agent '{agent_id}' is not reachable")
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(connector.dispatch(task["description"]))
    finally:
        loop.close()


def _run(task_id: str):
    """Execute one task synchronously. Updates in-memory state before and after."""
    with _lock:
        task = _state.get(task_id)
        if not task:
            return
        if task["status"] == "running":
            return  # already in flight
        task["status"]   = "running"
        task["last_run"] = datetime.now().isoformat(timespec="seconds")
        snapshot = dict(task)

    try:
        result = _dispatch_sync(snapshot)
        with _lock:
            _state[task_id]["status"]      = "completed"
            _state[task_id]["last_result"] = result
            _state[task_id]["last_error"]  = None
    except Exception as e:
        with _lock:
            _state[task_id]["status"]     = "failed"
            _state[task_id]["last_error"] = str(e)


def trigger(task_id: str) -> bool:
    """Manually trigger a task. Returns False if task not found."""
    if task_id not in _state:
        return False
    t = threading.Thread(target=_run, args=(task_id,), daemon=True)
    t.start()
    return True


# ── Background scheduler ───────────────────────────────────────────────────────

class TaskExecutor(threading.Thread):
    """
    Watches interval tasks and fires them when their period elapses.
    Also fires on_start tasks once at launch.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self._stop     = threading.Event()
        self._last_run: dict[str, float] = {}

    def stop(self):
        self._stop.set()

    def run(self):
        # Fire on_start tasks immediately in background threads
        for task in get_all():
            if task.get("schedule") == "on_start":
                threading.Thread(target=_run, args=(task["id"],), daemon=True).start()

        while not self._stop.wait(10):  # check every 10 s
            now = time.time()
            for task in get_all():
                sched = task.get("schedule", "manual")
                if not sched.startswith("interval:"):
                    continue
                try:
                    interval = int(sched.split(":")[1])
                except (IndexError, ValueError):
                    continue
                last = self._last_run.get(task["id"], 0)
                if now - last >= interval:
                    self._last_run[task["id"]] = now
                    threading.Thread(target=_run, args=(task["id"],), daemon=True).start()
