#!/usr/bin/env python3
"""
Workspace Dashboard Server
Serves the monitoring dashboard and orchestrates all agent APIs.
"""
import os
import re
import json
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import agent_registry as registry
import alert_engine   as alerts
from agents.workspace.tools   import TOOL_DEFINITIONS, execute_tool, MEMORY_DIR, WORKSPACE_ROOT
from agents.workspace.monitor import WorkspaceMonitor

AGENT_DIR = Path(__file__).parent
CONFIG_DIR = AGENT_DIR / "config"
load_dotenv(AGENT_DIR / "agent.conf")

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFJA-Za-z]')
strip_ansi = lambda s: ANSI_RE.sub('', s)

# ── System prompt ──────────────────────────────────────────────────────────────
WORKSPACE_SYSTEM_PROMPT = f"""You are a Workspace Management Agent for a Docker-based development workspace.

Workspace root: {WORKSPACE_ROOT}
Your memory:    {MEMORY_DIR}
Today:          {datetime.now().strftime('%Y-%m-%d')}

YOUR PURPOSE:
Guardian of this workspace — understand its structure, track evolution,
detect problems early, and keep it clean and easy to clone and resume.

WORKSPACE STRUCTURE:
- dockerspace/     — workspace-level Docker setup
- projectspace/    — all active projects
  - ums/           — Spring Boot 3 / Java 21 User Management System
  - mypostgresql_db/ — PostgreSQL 16 dev container
  - ai-agents/claude-agent/ — Claude API testing agent
  - myapigw/       — API gateway
- workspace-agent/ — YOU live here

CONVENTIONS:
- Every project: build.sh, start.sh, stop.sh, health.sh, login_docker.sh
- Shared Docker network: ums-network
- Config: agent.conf for AI agents, project.conf for Docker containers
- No hardcoded IPs — use container names on shared networks

RESPONSIBILITIES:
1. OBSERVE — Scan structure and git history
2. REMEMBER — Save findings to memory/ before ending
3. DETECT — Mass deletions, wrong locations, hardcoded values, broken conventions
4. ADVISE — Specific fixes with file/line references
5. INFORM — Keep meta.json current for other agents

MEMORY: workspace_structure.md, projects.md, change_log.md, concerns.md, sessions.md, meta.json
RULE: Always read memory first. Always save before ending.
"""

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Workspace Dashboard")
app.mount("/static", StaticFiles(directory=str(AGENT_DIR / "static")), name="static")


@app.on_event("startup")
async def startup():
    MEMORY_DIR.mkdir(exist_ok=True)
    loop = asyncio.get_event_loop()
    alerts.init(loop)

    # Background workspace file monitor (silent → pushes workspace_change events)
    monitor = WorkspaceMonitor(WORKSPACE_ROOT, MEMORY_DIR, on_change=alerts.on_workspace_change)
    monitor.start()
    app.state.monitor = monitor

    # Background agent status poller (pushes status_change + alert events)
    poller = alerts.AlertPoller()
    poller.start()
    app.state.poller = poller


@app.on_event("shutdown")
async def shutdown():
    for attr in ("monitor", "poller"):
        obj = getattr(app.state, attr, None)
        if obj:
            obj.stop()


# ── Dashboard ──────────────────────────────────────────────────────────────────
@app.get("/")
async def index():
    return HTMLResponse((AGENT_DIR / "static" / "index.html").read_text())


# ── Agent API ──────────────────────────────────────────────────────────────────
@app.get("/api/agents")
async def list_agents():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, registry.get_all_info)
    return {"agents": data}


@app.post("/api/agents/{agent_id}/start")
async def start_agent(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec:
        return JSONResponse({"error": "not found"}, 404)
    loop = asyncio.get_event_loop()
    try:
        if spec.type == "docker":
            r = await loop.run_in_executor(None, lambda: subprocess.run(
                ["docker", "start", spec.container],
                capture_output=True, text=True, timeout=20,
            ))
            return {"ok": r.returncode == 0, "detail": r.stderr.strip() or "started"}
        return {"ok": False, "detail": "Host agents start via terminal or ./start.sh"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec:
        return JSONResponse({"error": "not found"}, 404)
    loop = asyncio.get_event_loop()
    try:
        if spec.type == "docker":
            await loop.run_in_executor(None, lambda: subprocess.run(
                ["docker", "stop", spec.container], capture_output=True, timeout=30,
            ))
        else:
            await loop.run_in_executor(None, lambda: subprocess.run(
                ["pkill", "-f", spec.host_script], capture_output=True, timeout=5,
            ))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Log stream (SSE) ───────────────────────────────────────────────────────────
@app.get("/api/agents/{agent_id}/logs/stream")
async def stream_logs(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)

    async def docker_gen(container):
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "-f", "--tail", "100", container,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            async for raw in proc.stdout:
                line = strip_ansi(raw.decode(errors="replace"))
                yield f"data: {json.dumps({'line': line})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'line': f'[error] {e}\n'})}\n\n"

    async def file_gen(log_path: Path):
        if log_path.exists():
            for line in log_path.read_text().splitlines()[-100:]:
                yield f"data: {json.dumps({'line': line + chr(10)})}\n\n"
        cursor = log_path.stat().st_size if log_path.exists() else 0
        while True:
            await asyncio.sleep(2)
            if log_path.exists():
                content = log_path.read_text()
                if len(content) > cursor:
                    for line in content[cursor:].splitlines():
                        yield f"data: {json.dumps({'line': line + chr(10)})}\n\n"
                    cursor = len(content)
            yield ": keepalive\n\n"

    async def empty_gen():
        yield f"data: {json.dumps({'line': 'No log source configured.\n'})}\n\n"
        while True:
            await asyncio.sleep(30)
            yield ": keepalive\n\n"

    if not spec:
        gen = empty_gen()
    elif spec.type == "docker":
        gen = docker_gen(spec.container)
    elif spec.log_file:
        gen = file_gen(Path(spec.log_file))
    else:
        gen = empty_gen()

    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Memory API ─────────────────────────────────────────────────────────────────
@app.get("/api/agents/{agent_id}/memory")
async def list_memory(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec or not spec.memory_dir:
        return {"files": []}
    mem = Path(spec.memory_dir)
    if not mem.exists():
        return {"files": []}
    return {"files": [f.name for f in sorted(mem.iterdir()) if f.is_file()]}


@app.get("/api/agents/{agent_id}/memory/{filename}")
async def read_memory(agent_id: str, filename: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec or not spec.memory_dir:
        return {"error": "no memory dir"}
    path = Path(spec.memory_dir) / filename
    if not path.exists():
        return {"error": "not found"}
    return {"filename": filename, "content": path.read_text()}


# ── Alert settings API ─────────────────────────────────────────────────────────
def _load_alert_settings() -> dict:
    path = CONFIG_DIR / "alerts.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _save_alert_settings(data: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    (CONFIG_DIR / "alerts.json").write_text(json.dumps(data, indent=2))


@app.get("/api/alerts/settings")
async def get_alert_settings():
    return _load_alert_settings()


@app.put("/api/alerts/settings")
async def update_alert_settings(body: dict):
    _save_alert_settings(body)
    return {"ok": True}


@app.post("/api/alerts/test/{alert_type}")
async def test_alert(alert_type: str):
    alerts.broadcast({
        "type":       "alert",
        "id":         "test",
        "alert_type": alert_type,
        "severity":   "critical" if alert_type == "alarm" else "warning",
        "agent_id":   "test",
        "agent_name": "Test",
        "message":    f"Test alert: {alert_type}",
        "ts":         datetime.now().isoformat(),
    })
    return {"ok": True}


# ── Event stream — alerts + status changes + workspace changes (SSE) ───────────
@app.get("/api/events/stream")
async def events_stream():
    q = alerts.subscribe()

    async def generate():
        try:
            # Send current agent states immediately on connect
            data = await asyncio.get_event_loop().run_in_executor(None, registry.get_all_info)
            yield f"data: {json.dumps({'type': 'init', 'agents': data})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            alerts.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Chat WebSocket ─────────────────────────────────────────────────────────────
async def _workspace_turn(ws, history, client):
    loop = asyncio.get_event_loop()
    while True:
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model="claude-sonnet-4-6", max_tokens=8096,
            system=WORKSPACE_SYSTEM_PROMPT, tools=TOOL_DEFINITIONS, messages=history,
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


async def _container_turn(ws, spec, message):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-e", f"ANTHROPIC_API_KEY={api_key}",
            "-i", spec.container, "bash", spec.container_script, message,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in proc.stdout:
            line = strip_ansi(raw.decode(errors="replace"))
            if line.strip():
                await ws.send_json({"type": "text", "content": line})
        await proc.wait()
    except Exception as e:
        await ws.send_json({"type": "error", "content": str(e)})
    await ws.send_json({"type": "done"})


@app.websocket("/ws/agents/{agent_id}/chat")
async def agent_chat(ws: WebSocket, agent_id: str):
    await ws.accept()
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec:
        await ws.send_json({"type": "error", "content": f"Unknown agent: {agent_id}"})
        await ws.close()
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        await ws.send_json({"type": "error", "content": "ANTHROPIC_API_KEY not set"})
        await ws.close()
        return

    client  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = []
    try:
        while True:
            data = await ws.receive_text()
            text = json.loads(data).get("content", "").strip()
            if not text:
                continue
            if spec.type == "host" and spec.id == "workspace":
                history.append({"role": "user", "content": text})
                history = await _workspace_turn(ws, history, client)
            elif spec.type == "docker":
                await _container_turn(ws, spec, text)
            else:
                await ws.send_json({"type": "error", "content": "Chat not supported for this agent"})
                await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
