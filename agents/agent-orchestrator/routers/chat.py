import json
import os
import re
from datetime import datetime
from pathlib import Path

import anthropic
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import agent_registry as registry
from workspace.tools import TOOL_DEFINITIONS, execute_tool, MEMORY_DIR, WORKSPACE_ROOT

router = APIRouter(tags=["chat"])

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFJA-Za-z]')
_strip = lambda s: _ANSI_RE.sub('', s)

# ── Memory paths ──────────────────────────────────────────────────────────────

_SESSIONS_LOG = (
    Path(__file__).resolve().parent.parent.parent
    / "workspace-agent/workspace/memory/sessions.md"
)

_ORCHESTRATOR_MEMORY = Path(__file__).resolve().parent.parent / "memory"
_ORCHESTRATOR_CHAT_LOG = _ORCHESTRATOR_MEMORY / "chat_history.log"
_WORKSPACE_CHAT_LOG    = (
    Path(__file__).resolve().parent.parent.parent
    / "workspace-agent/workspace/memory/chat_history.log"
)
_HIST_MAX_TURNS = 30


def _log(entry: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(_SESSIONS_LOG, "a") as f:
        f.write(f"\n**{ts}** {entry}\n")


def _append_chat(log_path: Path, role: str, content: str):
    """Append one message to a JSONL chat history file."""
    log_path.parent.mkdir(exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = json.dumps({"ts": ts, "role": role, "content": content}, ensure_ascii=False)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_chat(log_path: Path) -> list:
    """Return last _HIST_MAX_TURNS exchanges from a JSONL chat history file."""
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
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


def _log_task(agent_id: str, task: str, result: dict):
    """Append one dispatch record to the orchestrator task log."""
    _ORCHESTRATOR_MEMORY.mkdir(exist_ok=True)
    log = _ORCHESTRATOR_MEMORY / "tasks.md"
    ts     = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = "error" if "error" in result else "ok"
    body   = result.get("error") or str(result.get("result", ""))
    entry  = (
        f"\n---\n**{ts}** → `{agent_id}` [{status}]\n"
        f"Task: {task}\n"
        f"{'Error' if status == 'error' else 'Result'}: "
        f"{body[:400]}{'…' if len(body) > 400 else ''}\n"
    )
    existing = log.read_text() if log.exists() else "# Orchestrator Task Log\n"
    log.write_text(existing + entry)


# ═════════════════════════════════════════════════════════════════════════════
# Direct workspace chat (unchanged behaviour — preserved for backward compat)
# ═════════════════════════════════════════════════════════════════════════════

_WORKSPACE_SYSTEM = f"""You are a Workspace Management Agent for a Docker-based development workspace.

Workspace root: {WORKSPACE_ROOT}
Your memory:    {MEMORY_DIR}
Today:          {datetime.now().strftime('%Y-%m-%d')}

YOUR PURPOSE:
Guardian of this workspace — understand its structure, track evolution,
detect problems early, and keep it clean and easy to clone and resume.

WORKSPACE STRUCTURE:
- dockerspace/       — workspace-level Docker setup
- projectspace/      — all active projects
  - ums/             — Spring Boot 3 / Java 21 User Management System
  - mypostgresql_db/ — PostgreSQL 16 dev container
  - ai-agents/       — Claude API testing agents
  - myapigw/         — API gateway
- agents/            — agent-orchestrator and workspace-agent live here

CONVENTIONS:
- Every project: build.sh, start.sh, stop.sh, health.sh
- Shared Docker network: ums-network
- Config: shared.conf for API keys, server.conf for server settings
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


async def _workspace_turn(ws, history, client, user_msg: str):
    _append_chat(_WORKSPACE_CHAT_LOG, "user", user_msg)
    _log(f"— user: {user_msg}")
    import asyncio
    loop = asyncio.get_event_loop()
    while True:
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model="claude-sonnet-4-6", max_tokens=8096,
            system=_WORKSPACE_SYSTEM, tools=TOOL_DEFINITIONS, messages=history,
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
                _append_chat(_WORKSPACE_CHAT_LOG, "assistant", final)
                _log(f"— agent: {final[:300]}{'…' if len(final) > 300 else ''}")
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


# ═════════════════════════════════════════════════════════════════════════════
# Orchestrator brain
# ═════════════════════════════════════════════════════════════════════════════

# The one tool the orchestrator LLM can call — dispatch a task to any agent.
# Add more tools here if you need the orchestrator to do things directly
# (e.g. send_email, write_report). Keep agent-specific work inside connectors.
_ORCHESTRATOR_TOOLS = [
    {
        "name": "dispatch_to_agent",
        "description": (
            "Send a task to a specific agent and receive its full response. "
            "Use when the task matches that agent's documented capabilities. "
            "For multi-step tasks, dispatch sequentially and pass results forward."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the target agent exactly as listed in available agents"
                },
                "task": {
                    "type": "string",
                    "description": "Clear, self-contained task for the agent — include any context it needs"
                }
            },
            "required": ["agent_id", "task"]
        }
    }
]


def _build_orchestrator_prompt() -> str:
    """Build system prompt dynamically from the live agent registry."""
    lines = []
    for spec in registry.AGENT_SPECS:
        if spec.connector in ("orchestrator", "none") or not spec.capabilities:
            continue
        with registry._lock:
            state  = registry._states.get(spec.id)
            status = f" [{state.status}]" if state else ""
        lines.append(f"  {spec.id}{status}: {spec.name}\n    Can do: {spec.capabilities}")

    agents_block = "\n".join(lines) if lines else "  (no agents with capabilities configured)"

    return f"""You are the Orchestrator for this workspace. You coordinate specialized agents to complete tasks.

Today: {datetime.now().strftime('%Y-%m-%d %H:%M')}

AVAILABLE AGENTS:
{agents_block}

YOUR ROLE:
- Receive a task from the user
- Decide which agent(s) can handle it and in what order
- Dispatch each subtask using dispatch_to_agent
- Synthesize the results into one clear response for the user

DISPATCH RULES:
- Match tasks strictly to agent capabilities — do not dispatch outside documented capabilities
- For multi-step work: chain dispatches (use one agent's output as input for the next)
- If an agent is [stopped]: mention it in your response, do not dispatch to it
- Always synthesize — never relay raw agent output directly; explain what happened

RESPONSE STYLE:
- Be concise: what was done, by which agent, and what the result was
- Include detail only if the user asked for it
- On failure: say what failed and what (if anything) was done instead
"""


async def _dispatch(agent_id: str, task: str) -> dict:
    """Route one task to an agent via its connector. Logs the result."""
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec:
        result = {"error": f"Unknown agent: '{agent_id}'. Check available agents in agents.conf."}
        return result

    connector = registry.make_connector(spec)
    if not connector:
        result = {"error": f"Agent '{agent_id}' has no connector (connector={spec.connector!r}). "
                           "Set connector_module / api_url / connector_cmd in agents.conf."}
        _log_task(agent_id, task, result)
        return result

    if not connector.is_available():
        result = {"error": f"Agent '{agent_id}' is not reachable. Start it first."}
        _log_task(agent_id, task, result)
        return result

    try:
        text   = await connector.dispatch(task)
        result = {"agent": agent_id, "result": text}
    except Exception as e:
        result = {"error": f"Dispatch to '{agent_id}' raised: {e}"}

    _log_task(agent_id, task, result)
    return result


async def _orchestrator_turn(ws, history, client, user_msg: str):
    _append_chat(_ORCHESTRATOR_CHAT_LOG, "user", user_msg)
    _log(f"[orchestrator] user: {user_msg}")
    import asyncio
    loop = asyncio.get_event_loop()
    system = _build_orchestrator_prompt()

    while True:
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model="claude-sonnet-4-6", max_tokens=8096,
            system=system, tools=_ORCHESTRATOR_TOOLS, messages=history,
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
                _append_chat(_ORCHESTRATOR_CHAT_LOG, "assistant", final)
                _log(f"[orchestrator] done: {final[:200]}{'…' if len(final) > 200 else ''}")
            break

        history.append({"role": "assistant", "content": resp.content})
        results = []
        for b in tool_calls:
            await ws.send_json({"type": "tool_call", "id": b.id, "name": b.name, "input": b.input})
            if b.name == "dispatch_to_agent":
                result = await _dispatch(b.input.get("agent_id", ""), b.input.get("task", ""))
            else:
                result = {"error": f"Unknown orchestrator tool: {b.name}"}
            await ws.send_json({"type": "tool_result", "id": b.id, "name": b.name, "result": result})
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(result)})
        history.append({"role": "user", "content": results})

    await ws.send_json({"type": "done"})
    return history


# ═════════════════════════════════════════════════════════════════════════════
# WebSocket endpoint
# ═════════════════════════════════════════════════════════════════════════════

async def _ws_proxy_session(client_ws: WebSocket, spec):
    """Proxy the entire WS session to an HTTP agent's /ws/chat endpoint."""
    import asyncio
    import websockets
    ws_url = spec.api_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://") + "/ws/chat"
    try:
        async with websockets.connect(ws_url) as agent_ws:
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
        await client_ws.send_json({"type": "error", "content": f"Cannot reach {spec.name}: {e}"})
        await client_ws.send_json({"type": "done"})


@router.websocket("/ws/agents/{agent_id}/chat")
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

    # HTTP agents: proxy the full session to the agent's own /ws/chat endpoint
    if spec.connector == "http" and spec.api_url:
        await _ws_proxy_session(ws, spec)
        return

    client  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = []

    # Replay persisted chat history (workspace + orchestrator)
    if spec.id in ("orchestrator", "workspace"):
        log_path = _ORCHESTRATOR_CHAT_LOG if spec.id == "orchestrator" else _WORKSPACE_CHAT_LOG
        saved    = _load_chat(log_path)
        history  = [{"role": m["role"], "content": m["content"]} for m in saved]
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

            if spec.id == "workspace":
                # Direct chat — workspace-agent handles it without routing
                history = await _workspace_turn(ws, history, client, text)

            elif spec.id == "orchestrator":
                # Orchestrator chat — routes to best agent via connectors
                history = await _orchestrator_turn(ws, history, client, text)

            else:
                await ws.send_json({
                    "type": "error",
                    "content": f"'{spec.name}' has no chat handler (connector={spec.connector!r}).",
                })
                await ws.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
