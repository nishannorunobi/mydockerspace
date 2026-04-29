"""
Docker Orchestrator Agent — FastAPI server.

API endpoints:
  GET  /health                          health check
  GET  /api/status                      full snapshot (docker_status.json)
  GET  /api/containers                  all containers + live stats
  GET  /api/containers/{name}           single container detail + stats
  GET  /api/containers/{name}/logs      recent log output
  GET  /api/containers/{name}/history   snapshot history from DB
  POST /api/containers/{name}/restart   restart a container
  GET  /api/events                      recent events (all or filtered)
  POST /api/tasks                       natural language task → AI agent response
"""
import asyncio
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
import anthropic as _anthropic

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Path + config ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR.parent.parent / "shared.conf")
load_dotenv(BASE_DIR.parent / "server.conf")

import database as db
import agent as ai_agent
from monitor import DockerMonitor, list_containers, get_stats, get_logs, restart_container, STATUS_FILE
from tools import TOOL_DEFINITIONS, execute_tool

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
app = FastAPI(title="Docker Orchestrator Agent", version="1.0")
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


@app.on_event("startup")
async def startup():
    db.init()
    monitor = DockerMonitor(on_event=_send_notification)
    monitor.start()
    app.state.monitor = monitor


@app.on_event("shutdown")
async def shutdown():
    monitor = getattr(app.state, "monitor", None)
    if monitor:
        monitor.stop()


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "docker-orchestrator", "time": datetime.now().isoformat()}


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


@app.post("/api/containers/{name}/restart")
def restart_one(name: str):
    """Manually restart a container."""
    ok, msg = restart_container(name)
    event   = "manually_restarted" if ok else "manual_restart_failed"
    db.log_event(name, name, event, "via API")
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "container": name, "message": msg}


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
    while True:
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=ai_agent.SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=history,
        ))
        tool_calls  = [b for b in resp.content if b.type == "tool_use"]
        text_blocks = [b for b in resp.content if b.type == "text"]

        for b in text_blocks:
            if b.text.strip():
                await ws.send_json({"type": "text", "content": b.text})

        if resp.stop_reason == "end_turn" or not tool_calls:
            final = " ".join(b.text for b in text_blocks).strip()
            if final:
                history.append({"role": "assistant", "content": final})
                _append_chat("assistant", final)
            break

        history.append({"role": "assistant", "content": resp.content})
        results = []
        for b in tool_calls:
            await ws.send_json({"type": "tool_call", "id": b.id, "name": b.name, "input": b.input})
            result = await loop.run_in_executor(None, lambda blk=b: execute_tool(blk.name, blk.input))
            await ws.send_json({"type": "tool_result", "id": b.id, "name": b.name, "result": result})
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(result)})
        history.append({"role": "user", "content": results})

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
