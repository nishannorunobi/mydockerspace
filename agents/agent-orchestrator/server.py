#!/usr/bin/env python3
"""
Agent Orchestrator — Server Entry Point
Routes live in routers/. Tasks defined in tasks.json. Agents defined in agents.conf.
"""
import sys
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
# workspace-agent root — for "from workspace.X import ..." style imports
sys.path.insert(0, str(BASE_DIR.parent / "workspace-agent"))
# workspace-agent/workspace — for bare "from tools import ..." inside workspace/agent.py
sys.path.insert(0, str(BASE_DIR.parent / "workspace-agent" / "workspace"))

# ── Config (shared API key + server settings) ──────────────────────────────────
load_dotenv(BASE_DIR.parent / "shared.conf")
load_dotenv(BASE_DIR / "server.conf")

import os
STATIC_DIR = BASE_DIR / os.getenv("STATIC_DIR", "static")
LOG_DIR    = BASE_DIR / os.getenv("LOG_DIR",    "logs")

# ── Shared services ───────────────────────────────────────────────────────────
import alert_engine as alert_eng
from workspace.monitor import WorkspaceMonitor
from workspace.tools   import WORKSPACE_ROOT, MEMORY_DIR

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Agent Orchestrator",
    version="2.0",
    description="Orchestrates agents, manages tasks, monitors the workspace.",
    docs_url="/docs",
    redoc_url="/redoc",
)


class NoCacheStatic(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"]        = "no-cache"
            response.headers["Expires"]       = "0"
        return response


app.add_middleware(NoCacheStatic)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
from routers import agents, alerts, events, chat, tasks

app.include_router(agents.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(tasks.router,  prefix="/api")
app.include_router(chat.router)


# ── Frontend ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text()


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    LOG_DIR.mkdir(exist_ok=True)
    MEMORY_DIR.mkdir(exist_ok=True)
    loop = asyncio.get_event_loop()
    alert_eng.init(loop)

    monitor = WorkspaceMonitor(WORKSPACE_ROOT, MEMORY_DIR, on_change=alert_eng.on_workspace_change)
    monitor.start()
    app.state.monitor = monitor

    poller = alert_eng.AlertPoller()
    poller.start()
    app.state.poller = poller

    # Task executor — reads tasks.json, runs scheduled and on_start tasks
    from managers.task_executor import TaskExecutor, init as task_init
    task_init()
    executor = TaskExecutor()
    executor.start()
    app.state.executor = executor


@app.on_event("shutdown")
async def shutdown():
    for attr in ("monitor", "poller", "executor"):
        obj = getattr(app.state, attr, None)
        if obj:
            obj.stop()


@app.get("/health")
def health():
    return {"status": "ok", "service": "agent-orchestrator"}
