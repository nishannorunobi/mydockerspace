"""
Agent Registry — defines all known agents and tracks their runtime state.
Add new agents by appending to AGENT_SPECS. No other file needs to change.
"""
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

WORKSPACE_ROOT = Path(__file__).parent.parent
AGENT_DIR      = Path(__file__).parent


@dataclass
class AgentSpec:
    id:          str
    name:        str
    description: str
    type:        str          # "host" | "docker"
    # host agents
    host_script: Optional[str] = None
    log_file:    Optional[str] = None
    # docker agents
    container:        Optional[str] = None
    container_script: Optional[str] = None
    # shared
    memory_dir: Optional[str] = None


@dataclass
class AgentState:
    status:      str       = "unknown"
    prev_status: str       = "unknown"
    uptime_start:   Optional[datetime] = None
    downtime_start: Optional[datetime] = None
    last_check:  datetime  = field(default_factory=datetime.now)

    def uptime(self) -> str:
        if self.status != "running" or not self.uptime_start:
            return "—"
        delta = datetime.now() - self.uptime_start
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        if h:  return f"{h}h {m}m"
        if m:  return f"{m}m"
        return "<1m"

    def downtime(self) -> str:
        if self.status == "running" or not self.downtime_start:
            return "—"
        secs = int((datetime.now() - self.downtime_start).total_seconds())
        m = secs // 60
        if m < 1:  return "just now"
        h = m // 60
        if h:  return f"{h}h {m % 60}m ago"
        return f"{m}m ago"

    def uptime_pct(self) -> Optional[float]:
        """Rough uptime % since first seen (placeholder for future metric)."""
        return None


# ── Registry ───────────────────────────────────────────────────────────────────
# Add new agents here. Everything else auto-discovers them.

AGENT_SPECS: List[AgentSpec] = [
    AgentSpec(
        id="workspace",
        name="Workspace Agent",
        description="Monitors workspace structure, git history, and project conventions",
        type="host",
        host_script=str(AGENT_DIR / "agents/workspace/agent.py"),
        log_file=str(AGENT_DIR / "agents/workspace/memory/sessions.md"),
        memory_dir=str(AGENT_DIR / "agents/workspace/memory"),
    ),
    AgentSpec(
        id="db",
        name="PostgreSQL DB Agent",
        description="Manages the UMS database — queries, health, schema, cross-container comms",
        type="docker",
        container="mypostgresql_db-container",
        container_script="/mypostgresql_db/db-agent/start.sh",
        memory_dir=str(WORKSPACE_ROOT / "projectspace/mypostgresql_db/db-agent/memory"),
    ),
    AgentSpec(
        id="claude-test",
        name="Claude Test Agent",
        description="Tests UMS REST API endpoints via HTTP",
        type="host",
        host_script=str(WORKSPACE_ROOT / "projectspace/ai-agents/claude-agent/host/start.sh"),
        memory_dir=None,
    ),
]

SPEC_BY_ID: Dict[str, AgentSpec] = {s.id: s for s in AGENT_SPECS}

# ── State store (all access must go through helpers below) ─────────────────────
_states: Dict[str, AgentState] = {s.id: AgentState() for s in AGENT_SPECS}
_lock   = threading.Lock()


# ── Status detection ───────────────────────────────────────────────────────────

def _detect(spec: AgentSpec) -> str:
    try:
        if spec.type == "docker":
            r = subprocess.run(
                ["docker", "inspect", "--format={{.State.Running}}", spec.container],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                return "unavailable"
            return "running" if r.stdout.strip() == "true" else "stopped"
        else:
            r = subprocess.run(
                ["pgrep", "-f", spec.host_script],
                capture_output=True, timeout=5,
            )
            return "running" if r.returncode == 0 else "stopped"
    except Exception:
        return "unknown"


def refresh_all() -> List[dict]:
    """
    Check every agent. Returns a list of status-change events for any agent
    whose status differs from last check. Thread-safe.
    """
    events = []
    for spec in AGENT_SPECS:
        new_status = _detect(spec)
        with _lock:
            state = _states[spec.id]
            prev  = state.status
            if new_status != prev:
                state.prev_status = prev
                state.status      = new_status
                if new_status == "running":
                    state.uptime_start   = datetime.now()
                    state.downtime_start = None
                else:
                    state.downtime_start = datetime.now()
                    state.uptime_start   = None
                events.append({
                    "type":        "status_change",
                    "agent_id":    spec.id,
                    "agent_name":  spec.name,
                    "status":      new_status,
                    "prev_status": prev,
                })
            elif new_status == "running" and state.uptime_start is None:
                state.uptime_start = datetime.now()
            state.last_check = datetime.now()
    return events


def get_all_info() -> List[dict]:
    """Return serialisable snapshot of all agents for the API."""
    with _lock:
        result = []
        for spec in AGENT_SPECS:
            state = _states[spec.id]
            mem_files: List[str] = []
            if spec.memory_dir and Path(spec.memory_dir).exists():
                mem_files = [f.name for f in sorted(Path(spec.memory_dir).iterdir()) if f.is_file()]
            result.append({
                "id":          spec.id,
                "name":        spec.name,
                "description": spec.description,
                "type":        spec.type,
                "container":   spec.container,
                "status":      state.status,
                "uptime":      state.uptime(),
                "downtime":    state.downtime(),
                "last_check":  state.last_check.strftime("%H:%M:%S"),
                "mem_files":   mem_files,
            })
        return result
