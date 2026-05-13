"""
Docker Manager Agent — FastAPI server.

API endpoints:
  GET  /health                          health check
  GET  /api/status                      full snapshot (docker_status.json)
  GET  /api/containers                  all containers + live stats
  GET  /api/containers/{name}           single container detail + stats
  GET  /api/containers/{name}/logs      recent log output
  GET  /api/containers/{name}/history   snapshot history from DB
  POST /api/containers/{name}/start     start a container
  POST /api/containers/{name}/stop      stop a container
  POST /api/containers/{name}/restart   restart a container
  GET  /api/events                      recent events (all or filtered)
  POST /api/tasks                       natural language task → AI agent response
  GET  /api/db-agent/health             proxy: db-agent liveness + postgres state
  POST /api/db-agent/db/start           proxy: start PostgreSQL inside DB container
  POST /api/db-agent/db/stop            proxy: stop PostgreSQL inside DB container
  POST /api/db-agent/tasks              proxy: AI task for db-agent
  WS   /api/db-agent/ws/chat            proxy: streaming chat with db-agent
"""
import asyncio
import json
import os
import smtplib
import subprocess
import sys
import threading
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
import anthropic as _anthropic

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

# ── Path + config ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR.parent.parent / "shared.conf")
load_dotenv(BASE_DIR.parent / "server.conf")

import database as db
import agent as ai_agent
import port_forward as pf
from monitor import DockerMonitor, list_containers, get_stats, get_logs, restart_container, start_container, stop_container, STATUS_FILE
from tools import TOOL_DEFINITIONS, execute_tool

_ROUTER_DIR = BASE_DIR.parent.parent / "llm-router"
sys.path.insert(0, str(_ROUTER_DIR))
from router import get_router as _get_router

# ── Chat history ───────────────────────────────────────────────────────────────
_CHAT_HISTORY_LOG = BASE_DIR / "memory" / "chat_history.log"
_HIST_MAX_TURNS   = 30


def _append_chat(role: str, content: str):
    _CHAT_HISTORY_LOG.parent.mkdir(exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = json.dumps({"ts": ts, "role": role, "content": content}, ensure_ascii=False)
    with open(_CHAT_HISTORY_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_chat_history() -> list:
    if not _CHAT_HISTORY_LOG.exists():
        return []
    lines = _CHAT_HISTORY_LOG.read_text(encoding="utf-8").splitlines()
    lines = lines[-(_HIST_MAX_TURNS * 2):]
    msgs  = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msgs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return msgs

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Docker Manager Agent", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Lifecycle ──────────────────────────────────────────────────────────────────

def _send_notification(container_name: str, event: str, detail: str):
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    notify    = os.environ.get("NOTIFY_EMAIL", smtp_user)
    if not smtp_user or not smtp_pass:
        return
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = MIMEText(
        f"Container : {container_name}\n"
        f"Event     : {event}\n"
        f"Time      : {ts}\n"
        f"Detail    : {detail}\n"
    )
    msg["Subject"] = f"[docker-agent] {container_name} — {event}"
    msg["From"]    = smtp_user
    msg["To"]      = notify
    try:
        with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                          int(os.environ.get("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except Exception:
        pass  # email is best-effort; container management continues regardless


_ORCHESTRATOR_EVENTS_URL  = "http://localhost:8888/api/events/notify"
_ORCHESTRATOR_ALERTS_URL  = "http://localhost:8888/api/alerts/ingest"
_alerted_issues: dict[str, set] = {}  # agent_id → set of active issue strings


def _post_to_orchestrator(url: str, body: dict):
    try:
        payload = json.dumps(body).encode()
        req = _urllib_req.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        _urllib_req.urlopen(req, timeout=5)
    except Exception:
        pass


def _poll_sub_agent_health():
    """Poll each registered sub-agent's /health, detect issues, forward to orchestrator."""
    try:
        registrations = db.get_agent_registrations()
    except Exception:
        return

    for reg in registrations:
        agent_id = reg["id"]
        base = _container_url(reg["container"], reg["port"], reg["network"])
        if not base:
            continue
        try:
            with _urllib_req.urlopen(f"{base}/health", timeout=5) as r:
                health = json.loads(r.read())
            current_issues = set(health.get("issues", []))
        except Exception:
            continue

        known = _alerted_issues.get(agent_id, set())
        new_issues    = current_issues - known
        cleared_issues = known - current_issues

        for issue in new_issues:
            _post_to_orchestrator(_ORCHESTRATOR_ALERTS_URL, {
                "severity":   "critical",
                "agent_id":   agent_id,
                "agent_name": reg.get("name", agent_id),
                "message":    f"{reg.get('name', agent_id)}: {issue}",
                "alert_type": "agent_issue",
            })

        if cleared_issues and not current_issues:
            _post_to_orchestrator(_ORCHESTRATOR_ALERTS_URL, {
                "severity":   "info",
                "agent_id":   agent_id,
                "agent_name": reg.get("name", agent_id),
                "message":    f"{reg.get('name', agent_id)} issues resolved — operating normally",
                "alert_type": "agent_recovered",
            })

        _alerted_issues[agent_id] = current_issues


def _notify_orchestrator(event: str, source: str, container: str, data: dict):
    """Push an event to the orchestrator SSE stream so the dashboard sees it."""
    try:
        payload = json.dumps({
            "source":    source,
            "event":     event,
            "container": container,
            "data":      data,
        }).encode()
        req = _urllib_req.Request(
            _ORCHESTRATOR_EVENTS_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        _urllib_req.urlopen(req, timeout=5)
    except Exception:
        pass  # best-effort; dashboard notification is non-critical


def _bell_rings() -> int:
    """Read BELL_RINGS from server.conf at call time so changes take effect without restart."""
    try:
        conf = (BASE_DIR.parent / "server.conf").read_text()
        for line in conf.splitlines():
            if line.strip().startswith("BELL_RINGS="):
                return max(1, int(line.split("=", 1)[1].strip()))
    except Exception:
        pass
    return 5


def _ring_bell():
    """Ring the host terminal bell N times (configurable via server.conf BELL_RINGS)."""
    n = _bell_rings()
    try:
        _sp.Popen(
            ["bash", "-c", f"for i in $(seq {n}); do printf '\\a'; sleep 0.3; done"],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
        )
    except Exception:
        pass


def _auto_resolve(task: str, source: str = "", container: str = "", event_data: dict = None):
    """Run the AI agent in a background thread to resolve a host-side issue autonomously."""
    try:
        history = ai_agent.run_agent(task, [])
        # Extract the AI's final response and forward it to the dashboard
        response = ""
        for msg in reversed(history):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    response = content.strip()
                    break
        _notify_orchestrator("auto_resolve_complete", source or "docker-manager",
                             container, {"summary": response[:500], "original": event_data or {}})
    except Exception as e:
        _notify_orchestrator("auto_resolve_failed", source or "docker-manager",
                             container, {"error": str(e), "original": event_data or {}})


@app.on_event("startup")
async def startup():
    pf.restore_from_disk()  # re-launch saved socat tunnels
    db.init()
    db.seed_default_agents()  # register db-agent + ums-agent if not already in DB
    monitor = DockerMonitor(on_event=_send_notification)
    monitor.start()
    app.state.monitor = monitor

    def _health_poll_loop():
        import time as _t
        _t.sleep(20)  # let agents settle on startup before first poll
        while True:
            _poll_sub_agent_health()
            _t.sleep(30)

    threading.Thread(target=_health_poll_loop, daemon=True, name="sub-agent-health-poller").start()


@app.on_event("shutdown")
async def shutdown():
    monitor = getattr(app.state, "monitor", None)
    if monitor:
        monitor.stop()


# ── Root ───────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return RedirectResponse(url="/docs")


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "docker-orchestrator", "time": datetime.now().isoformat()}


@app.get("/api/config")
def get_config():
    """Runtime-readable config values. Read from server.conf at request time — no restart needed."""
    return {"bell_rings": _bell_rings()}


# ── Status snapshot ────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    """Full docker_status.json — containers, counts, recent events."""
    if not STATUS_FILE.exists():
        return {"message": "Status not ready yet — monitor is starting up"}
    return json.loads(STATUS_FILE.read_text())


# ── All containers ─────────────────────────────────────────────────────────────

@app.get("/api/containers")
def get_all_containers():
    """List all containers (running + stopped) with live CPU/memory stats."""
    containers = list_containers(all_containers=True)
    stats_map  = {s["name"]: s for s in get_stats()}
    for c in containers:
        s = stats_map.get(c["name"], {})
        c["cpu"]     = s.get("cpu",     "—")
        c["memory"]  = s.get("memory",  "—")
        c["mem_pct"] = s.get("mem_pct", "—")
    return {
        "count":      len(containers),
        "running":    sum(1 for c in containers if "Up" in c.get("status", "")),
        "stopped":    sum(1 for c in containers if "Up" not in c.get("status", "")),
        "containers": containers,
    }


# ── Single container ───────────────────────────────────────────────────────────

@app.get("/api/containers/{name}")
def get_container(name: str):
    """Detail for one container — status, stats, and last 10 events from DB."""
    containers = list_containers(all_containers=True)
    match = next((c for c in containers if c["name"] == name or c["id"].startswith(name)), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Container '{name}' not found")

    stats_map = {s["name"]: s for s in get_stats()}
    s = stats_map.get(match["name"], {})
    match["cpu"]     = s.get("cpu",     "—")
    match["memory"]  = s.get("memory",  "—")
    match["mem_pct"] = s.get("mem_pct", "—")
    match["events"]  = db.get_events(limit=10, container_name=match["name"])
    return match


@app.get("/api/containers/{name}/logs")
def container_logs(name: str, lines: int = 100):
    """Recent stdout/stderr output from a container."""
    lines = min(lines, 500)
    return {"name": name, "lines": lines, "logs": get_logs(name, lines)}


@app.get("/api/containers/{name}/history")
def container_history(name: str, limit: int = 50):
    """Snapshot history for one container — status, CPU, memory over time."""
    snapshots = db.get_snapshots(container_name=name, limit=limit)
    if not snapshots:
        raise HTTPException(status_code=404, detail=f"No history found for '{name}'")
    return {"name": name, "count": len(snapshots), "history": snapshots}


@app.post("/api/containers/{name}/start")
def start_one(name: str):
    """Start a stopped container."""
    ok, msg = start_container(name)
    event   = "manually_started" if ok else "manual_start_failed"
    db.log_event(name, name, event, "via API")
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "container": name, "message": msg}


@app.post("/api/containers/{name}/stop")
def stop_one(name: str):
    """Stop a running container."""
    ok, msg = stop_container(name)
    event   = "manually_stopped" if ok else "manual_stop_failed"
    db.log_event(name, name, event, "via API")
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "container": name, "message": msg}


@app.post("/api/containers/{name}/restart")
def restart_one(name: str):
    """Manually restart a container."""
    ok, msg = restart_container(name)
    event   = "manually_restarted" if ok else "manual_restart_failed"
    db.log_event(name, name, event, "via API")
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "container": name, "message": msg}


@app.post("/api/containers/{name}/clean-restart")
def clean_restart_one(name: str):
    """
    Recreate a container from its compose/start scripts — picks up volume mounts,
    image rebuilds, and config changes that a plain `docker restart` misses.
    Runs in the background; returns immediately.
    """
    reg = db.get_registration_by_container(name)
    if not reg or not reg.get("compose_dir"):
        raise HTTPException(
            status_code=400,
            detail=f"No compose config registered for '{name}'. "
                   "Register the agent with compose_dir via POST /api/agents/register."
        )
    compose_dir = reg["compose_dir"]
    cmd         = reg.get("clean_restart_cmd") or "make restart"

    def _do_clean_restart():
        db.log_event(name, name, "clean_restart_started", f"cmd: {cmd} in {compose_dir}")
        try:
            result = subprocess.run(
                cmd, shell=True, cwd=compose_dir,
                capture_output=True, text=True, timeout=180,
            )
            out   = (result.stdout + result.stderr).strip()
            event = "clean_restarted" if result.returncode == 0 else "clean_restart_failed"
            db.log_event(name, name, event, out[:500])
        except subprocess.TimeoutExpired:
            db.log_event(name, name, "clean_restart_failed", "timed out after 180s")
        except Exception as e:
            db.log_event(name, name, "clean_restart_failed", str(e))

    threading.Thread(target=_do_clean_restart, daemon=True).start()
    return {"success": True, "container": name, "message": f"Clean restart started — rebuilding from {compose_dir}"}


# ── Events ─────────────────────────────────────────────────────────────────────

@app.get("/api/events")
def get_events(limit: int = 50, container: str = None):
    """
    Recent container events from the database.
    Optional ?container=name to filter to one container.
    """
    return {
        "count":  limit,
        "events": db.get_events(limit=limit, container_name=container),
    }


# ── Agent event bus ────────────────────────────────────────────────────────────
# Container-side agents POST here to trigger host-side actions.
# Reachable at http://172.19.0.1:8889/api/agent-events from inside any container.

class AgentEventBody(BaseModel):
    source:    str        # which agent fired this (e.g. "db-agent")
    event:     str        # event type: service_started | service_stopped | task_complete | ...
    container: str = ""  # container name — needed for port-forward IP resolution
    data:      dict = {} # event payload (service, port, host_port, label, ...)


@app.get("/api/agent-events")
def get_agent_events(limit: int = 50, source: str = None):
    """
    Telemetry log — all events fired by container and host agents.
    Filter by ?source=db-agent to see one agent's events only.
    """
    events = db.get_events(limit=limit)
    agent_events = [e for e in events if e.get("event_type", "").startswith("agent_event:")]
    if source:
        agent_events = [e for e in agent_events if source in e.get("container_name", "")]
    for e in agent_events:
        e["event"] = e.get("event_type", "").removeprefix("agent_event:")
        try:
            e["data"] = json.loads(e.get("details", "{}"))
        except Exception:
            e["data"] = {}
    return {"count": len(agent_events), "events": agent_events}


@app.post("/api/agent-events")
def handle_agent_event(body: AgentEventBody):
    """
    Cross-agent event bus — any agent (inside or outside a container) POSTs here.
    Handles: service_started (port-forward), service_stopped (close tunnel),
    install_error / action_required (AI auto-resolve), everything else (telemetry log).
    """
    _db_container = body.container or body.source
    db.log_event(_db_container, _db_container,
                 f"agent_event:{body.event}", json.dumps(body.data)[:500])
    # Always push telemetry to the dashboard SSE stream
    _notify_orchestrator(body.event, body.source, body.container, body.data)

    if body.event == "service_started":
        port      = body.data.get("port")
        host_port = body.data.get("host_port", port)
        label     = body.data.get("label") or body.data.get("service", "")
        if port and body.container:
            ip = _container_ip(body.container)
            if ip:
                result = pf.start(
                    host_port=int(host_port),
                    container_ip=ip,
                    container_port=int(port),
                    container=body.container,
                    label=label,
                )
                return {"ok": True, "event": body.event, "action": "port_forwarded", "result": result}
        return {"ok": True, "event": body.event, "action": "logged",
                "note": "no container/port specified — nothing to forward"}

    if body.event == "service_stopped":
        host_port = body.data.get("host_port") or body.data.get("port")
        if host_port:
            result = pf.stop(int(host_port))
            return {"ok": True, "event": body.event, "action": "port_forward_stopped", "result": result}
        return {"ok": True, "event": body.event, "action": "logged"}

    if body.event in ("install_error", "action_required"):
        # Container agent hit an error or needs something from the host.
        # Dispatch the AI agent to diagnose and fix it autonomously.
        task = (
            f"A container agent ({body.source}) inside {body.container or 'a container'} "
            f"reported an event: '{body.event}'. Details: {json.dumps(body.data)}. "
            f"Investigate the error and take whatever host-side or container-side actions "
            f"are needed to resolve it. Use run_host_command, exec_in_container, or "
            f"manage_port_forward as appropriate. "
            f"If you cannot resolve it without user help, call request_user_input to alert the user. "
            f"Proceed autonomously without asking for confirmation."
        )
        threading.Thread(
            target=_auto_resolve,
            args=(task,),
            kwargs={"source": body.source, "container": body.container, "event_data": body.data},
            daemon=True,
        ).start()
        return {"ok": True, "event": body.event, "action": "dispatched_to_ai",
                "note": "AI agent is resolving the issue autonomously"}

    if body.event == "user_intervention_required":
        _ring_bell()
        return {"ok": True, "event": body.event, "action": "bell_rung"}

    return {"ok": True, "event": body.event, "action": "logged"}


# ── Port forwarding ────────────────────────────────────────────────────────────

class PortForwardBody(BaseModel):
    container:      str
    container_port: int
    host_port:      int
    label:          str = ""


def _container_ip(container_name: str) -> str | None:
    try:
        r = _sp.run(
            ["docker", "inspect", container_name,
             "--format", "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        nets = json.loads(r.stdout.strip())
        for net in nets.values():
            ip = net.get("IPAddress", "")
            if ip:
                return ip
    except Exception:
        pass
    return None


@app.get("/api/port-forwards")
def list_port_forwards():
    return {"forwards": pf.list_forwards()}


@app.post("/api/port-forward")
def add_port_forward(body: PortForwardBody):
    ip = _container_ip(body.container)
    if not ip:
        return JSONResponse(
            {"ok": False, "error": f"Cannot resolve IP for container '{body.container}'"},
            status_code=400,
        )
    result = pf.start(
        host_port=body.host_port,
        container_ip=ip,
        container_port=body.container_port,
        container=body.container,
        label=body.label,
    )
    return result


@app.delete("/api/port-forward/{host_port}")
def remove_port_forward(host_port: int):
    return pf.stop(host_port)


# ── AI agent task endpoint (used by agent-orchestrator connector) ──────────────

class TaskRequest(BaseModel):
    task: str


@app.post("/api/tasks")
async def handle_task(body: TaskRequest):
    """
    Natural language task endpoint for the agent-orchestrator HTTP connector.
    The orchestrator POSTs {"task": "..."} here and gets back {"result": "..."}.
    """
    if not body.task.strip():
        raise HTTPException(status_code=400, detail="task field is required")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set")

    loop = asyncio.get_event_loop()
    history = await loop.run_in_executor(
        None, lambda: ai_agent.run_agent(body.task.strip(), [])
    )

    response = ""
    for msg in reversed(history):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                response = content.strip()
                break
            if isinstance(content, list):
                texts = [b["text"] for b in content
                         if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
                if texts:
                    response = " ".join(texts).strip()
                    break

    return {"result": response or "(no response)"}


# ── WebSocket chat (streaming, with conversation history) ──────────────────────

async def _chat_turn(ws: WebSocket, history: list, client) -> list:
    loop = asyncio.get_event_loop()

    async def _send_text(text):
        await ws.send_json({"type": "text", "content": text})

    async def _send_tool_call(b):
        await ws.send_json({"type": "tool_call", "id": b.id, "name": b.name, "input": b.input})

    async def _send_tool_result(b, result):
        await ws.send_json({"type": "tool_result", "id": b.id, "name": b.name, "result": result})

    def _tool_executor(name, inp):
        return execute_tool(name, inp)

    # Wrap async callbacks into sync callables for the router
    def on_text(text):
        asyncio.run_coroutine_threadsafe(_send_text(text), loop)
        _append_chat("assistant", text)

    def on_tool_call(b):
        asyncio.run_coroutine_threadsafe(_send_tool_call(b), loop)

    def on_tool_result(b, result):
        asyncio.run_coroutine_threadsafe(_send_tool_result(b, result), loop)

    _, history = await loop.run_in_executor(None, lambda: _get_router().agent_run(
        system        = ai_agent.SYSTEM_PROMPT,
        messages      = history,
        tools         = TOOL_DEFINITIONS,
        tool_executor = _tool_executor,
        on_text       = on_text,
        on_tool_call  = on_tool_call,
        on_tool_result= on_tool_result,
    ))

    await ws.send_json({"type": "done"})
    return history


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        await ws.send_json({"type": "error", "content": "ANTHROPIC_API_KEY not set"})
        await ws.close()
        return

    client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    saved   = _load_chat_history()
    history = [{"role": m["role"], "content": m["content"]} for m in saved]
    for m in saved:
        await ws.send_json({
            "type":    "history_msg",
            "role":    m["role"],
            "content": m["content"],
            "ts":      m.get("ts", ""),
        })

    try:
        while True:
            data = await ws.receive_text()
            text = json.loads(data).get("content", "").strip()
            if not text:
                continue
            history.append({"role": "user", "content": text})
            _append_chat("user", text)
            history = await _chat_turn(ws, history, client)
    except WebSocketDisconnect:
        pass


# ── Dynamic agent proxy ────────────────────────────────────────────────────────
# Agents are registered in SQLite (agent_registrations table).
# Any registered agent is proxied at /api/agents/{agent_id}/...
# No restart needed — register via POST /api/agents/register.

import time as _time
import urllib.request as _urllib_req
import urllib.error   as _urllib_err
import subprocess     as _sp

_AGENT_NETWORK = "ums-network"


def _container_url(container: str, port: int, network: str = _AGENT_NETWORK) -> str | None:
    """Resolve the container's IP on the given docker network and return its base URL."""
    try:
        r = _sp.run(
            ["docker", "inspect", container, "--format", "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        networks = json.loads(r.stdout.strip())
        ip = (networks.get(network) or {}).get("IPAddress", "")
        return f"http://{ip}:{port}" if ip else None
    except Exception:
        return None


def _agent_url(agent_id: str) -> str | None:
    reg = db.get_agent_registration(agent_id)
    if not reg:
        return None
    return _container_url(reg["container"], reg["port"], reg["network"])


# ── Agent registry API ─────────────────────────────────────────────────────────

class AgentRegistrationBody(BaseModel):
    id:         str
    name:       str
    container:  str
    port:       int
    agent_path: str
    network:    str = "ums-network"


@app.get("/api/registered-agents")
def list_registered_agents():
    return {"agents": db.get_agent_registrations()}


@app.post("/api/agents/register")
def register_agent(body: AgentRegistrationBody):
    db.register_agent(
        id=body.id, name=body.name, container=body.container,
        port=body.port, agent_path=body.agent_path, network=body.network,
    )
    return {"ok": True, "registered": body.id}


@app.delete("/api/agents/{agent_id}/unregister")
def unregister_agent(agent_id: str):
    if not db.get_agent_registration(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not registered")
    db.unregister_agent(agent_id)
    return {"ok": True, "unregistered": agent_id}


# ── Generic agent proxy ────────────────────────────────────────────────────────
# All HTTP paths under /api/agents/{agent_id}/ are proxied to the container agent.
# WebSocket at /api/agents/{agent_id}/ws/chat is proxied separately.
# Every request/response is logged to agent_comms in SQLite.

@app.websocket("/api/agents/{agent_id}/ws/chat")
async def agent_ws_chat(agent_id: str, client_ws: WebSocket):
    await client_ws.accept()
    import websockets as _ws

    reg = db.get_agent_registration(agent_id)
    if not reg:
        await client_ws.send_json({"type": "error", "content": f"Agent '{agent_id}' not registered"})
        await client_ws.send_json({"type": "done"})
        return

    base = _container_url(reg["container"], reg["port"], reg["network"])
    if not base:
        await client_ws.send_json({
            "type": "error",
            "content": f"Agent '{agent_id}' not reachable — is {reg['container']} running and agent built?",
        })
        await client_ws.send_json({"type": "done"})
        return

    db.log_agent_comm(agent_id, "ws", "/ws/chat", "session opened")
    ws_url = base.replace("http://", "ws://") + "/ws/chat"
    try:
        async with _ws.connect(ws_url) as agent_ws:
            async def _to_agent():
                try:
                    while True:
                        data = await client_ws.receive_text()
                        await agent_ws.send(data)
                except Exception:
                    pass

            async def _to_client():
                try:
                    async for raw in agent_ws:
                        text = raw if isinstance(raw, str) else raw.decode()
                        await client_ws.send_text(text)
                except Exception:
                    pass

            t1 = asyncio.create_task(_to_agent())
            t2 = asyncio.create_task(_to_client())
            await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
            for t in (t1, t2):
                t.cancel()
    except Exception as e:
        await client_ws.send_json({"type": "error", "content": f"Cannot reach {agent_id}: {e}"})
        await client_ws.send_json({"type": "done"})


@app.api_route("/api/agents/{agent_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def agent_proxy(agent_id: str, path: str, request: Request):
    # Special internal path — served locally, not proxied
    if path == "comms":
        limit = int(request.query_params.get("limit", 50))
        return JSONResponse({"agent_id": agent_id, "comms": db.get_agent_comms(agent_id, limit)})

    reg = db.get_agent_registration(agent_id)
    if not reg:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not registered")

    base = _container_url(reg["container"], reg["port"], reg["network"])
    if not base:
        return JSONResponse(
            {"error": f"Agent '{agent_id}' not reachable — is {reg['container']} running?"},
            status_code=503,
        )

    method  = request.method
    body    = await request.body()
    url     = f"{base}/{path}"
    t0      = _time.time()

    try:
        req = _urllib_req.Request(
            url,
            data=body if body else None,
            headers={"Content-Type": request.headers.get("content-type", "application/json")},
            method=method,
        )
        timeout = 90 if path.endswith("/tasks") else 15
        with _urllib_req.urlopen(req, timeout=timeout) as r:
            result_bytes = r.read()
            duration = int((_time.time() - t0) * 1000)
            db.log_agent_comm(
                agent_id=agent_id, direction="response",
                path=f"{method} /{path}",
                payload=body.decode(errors="replace") if body else "",
                result=result_bytes.decode(errors="replace"),
                duration_ms=duration,
            )
            return JSONResponse(json.loads(result_bytes))
    except _urllib_err.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        try:
            return JSONResponse(json.loads(err_body), status_code=e.code)
        except Exception:
            return JSONResponse({"error": f"HTTP {e.code}: {err_body[:300]}"}, status_code=e.code)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)
