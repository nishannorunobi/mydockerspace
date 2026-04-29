"""
Agent Registry — loads agent definitions from agents.conf.
To add or remove agents, edit agents.conf only. No code changes needed.
"""
import configparser
import subprocess
import threading

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

WORKSPACE_ROOT = Path(__file__).parent.parent.parent  # agent-orchestrator/ → agents/ → myworkspace/
AGENTS_DIR     = Path(__file__).parent.parent          # agent-orchestrator/ → agents/
AGENT_DIR      = Path(__file__).parent

_PATH_VARS = {
    "WORKSPACE_ROOT": str(WORKSPACE_ROOT),
    "AGENTS_DIR":     str(AGENTS_DIR),
    "AGENT_DIR":      str(AGENT_DIR),
}


def _resolve(val: Optional[str]) -> Optional[str]:
    if not val:
        return val
    for k, v in _PATH_VARS.items():
        val = val.replace(f"{{{k}}}", v)
    return val


@dataclass
class AgentSpec:
    id:            str
    name:          str
    description:   str
    home:          Optional[str] = None
    start_script:  Optional[str] = None
    stop_script:   Optional[str] = None
    health_script: Optional[str] = None
    log_file:      Optional[str] = None
    memory_dir:    Optional[str] = None
    # ── Orchestrator fields (configured in agents.conf) ───────────────────────
    capabilities:     str           = ""     # what this agent can do (shown to orchestrator LLM)
    connector:        str           = "none" # direct | http | subprocess | orchestrator | none
    connector_module: Optional[str] = None   # direct: dotted Python module path (e.g. workspace.agent)
    api_url:          Optional[str] = None   # http:   base URL of the agent's HTTP server
    connector_cmd:    Optional[str] = None   # subprocess: command relative to home


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
        return None


# ── Load specs from agents.conf ────────────────────────────────────────────────

def _load_specs() -> List[AgentSpec]:
    conf_path = AGENT_DIR / "agents.conf"
    parser = configparser.ConfigParser()
    parser.read(conf_path)

    specs = []
    for section in parser.sections():
        c = parser[section]
        specs.append(AgentSpec(
            id=section,
            name=c.get("name", section),
            description=c.get("description", ""),
            home=_resolve(c.get("home")),
            start_script=c.get("start_script"),
            stop_script=c.get("stop_script"),
            health_script=c.get("health_script"),
            log_file=_resolve(c.get("log_file")),
            memory_dir=_resolve(c.get("memory_dir")),
            capabilities=c.get("capabilities", ""),
            connector=c.get("connector", "none"),
            connector_module=c.get("connector_module"),
            api_url=c.get("api_url"),
            connector_cmd=c.get("connector_cmd"),
        ))
    return specs


AGENT_SPECS: List[AgentSpec] = _load_specs()
SPEC_BY_ID:  Dict[str, AgentSpec] = {s.id: s for s in AGENT_SPECS}

# ── State store ────────────────────────────────────────────────────────────────
_states: Dict[str, AgentState] = {s.id: AgentState() for s in AGENT_SPECS}
_lock   = threading.Lock()


def reload():
    """Reload AGENT_SPECS and SPEC_BY_ID from agents.conf (hot-reload after edits)."""
    new_specs = _load_specs()
    AGENT_SPECS[:] = new_specs
    SPEC_BY_ID.clear()
    SPEC_BY_ID.update({s.id: s for s in AGENT_SPECS})
    for s in AGENT_SPECS:
        if s.id not in _states:
            _states[s.id] = AgentState()


# ── Status detection ───────────────────────────────────────────────────────────

def _detect(spec: AgentSpec) -> str:
    # Orchestrator is embedded in the dashboard process — always running
    if spec.connector == "orchestrator":
        return "running"
    try:
        if not spec.home:
            return "unknown"
        r = subprocess.run(
            ["pgrep", "-f", spec.home],
            capture_output=True, timeout=5,
        )
        return "running" if r.returncode == 0 else "stopped"
    except Exception:
        return "unknown"


def make_connector(spec: AgentSpec):
    """
    Build the right AgentConnector for a spec based on agents.conf.
    Returns None if the spec has no connector configured.
    Add new connector types here as you add them to connectors/.
    """
    from connectors import DirectConnector, HttpConnector, SubprocessConnector
    if spec.connector == "direct" and spec.connector_module:
        return DirectConnector(spec.connector_module)
    if spec.connector == "http" and spec.api_url:
        return HttpConnector(spec.api_url)
    if spec.connector == "subprocess" and spec.connector_cmd and spec.home:
        return SubprocessConnector(spec.connector_cmd, spec.home)
    return None


def refresh_all() -> List[dict]:
    """Check every agent. Returns status-change events. Thread-safe."""
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
                "status":      state.status,
                "uptime":      state.uptime(),
                "downtime":    state.downtime(),
                "last_check":  state.last_check.strftime("%H:%M:%S"),
                "mem_files":   mem_files,
            })
        return result
