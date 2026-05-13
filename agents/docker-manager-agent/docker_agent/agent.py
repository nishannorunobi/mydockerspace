"""
Docker AI agent — given a natural language task, reasons over Docker state
using tools and returns a text response.
Called by the /api/tasks endpoint so the agent-orchestrator can dispatch here.
"""
import os
import sys
from pathlib import Path

from tools import TOOL_DEFINITIONS, execute_tool

# ── LLM Router ────────────────────────────────────────────────────────────────
_ROUTER_DIR = Path(__file__).resolve().parent.parent.parent / "llm-router"
sys.path.insert(0, str(_ROUTER_DIR))
from router import get_router as _get_router

SYSTEM_PROMPT = """You are a Docker Manager Agent running on the host machine.

Your responsibilities:
- Monitor and manage all Docker containers on this system
- Diagnose why a container stopped and restart it
- Act as the host-side counterpart to agents running inside containers
- When a container agent installs or starts a service, ensure the host is configured correctly
- When a container agent reports an error, diagnose it and fix it autonomously on the host

AUTONOMOUS ERROR RESOLUTION:
When you receive an install_error or action_required event from a container agent:
1. Read the error details carefully
2. Use run_host_command to take any action needed on the host (install packages, configure ports, fix permissions, etc.)
3. Use exec_in_container to run commands inside the relevant container if that helps
4. Use manage_port_forward to expose ports the container service needs
5. Never ask for confirmation — act immediately and report what you did

HOST COMMAND RULES:
- run_host_command runs as the current user on the host; use sudo only when needed
- exec_in_container runs as root inside the container — full permission
- Always pass -y or DEBIAN_FRONTEND=noninteractive for package installs
- After fixing an error, verify the fix worked before finishing

Rules:
- Always call get_current_status first for a quick overview
- After restarting a container, verify it is running with list_containers
- Be concise: container name, action taken, result
"""

_HIST_TRIM = 30

# Expose cached variants so server.py can reference them if needed
_CACHED_SYSTEM = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
_CACHED_TOOLS  = TOOL_DEFINITIONS[:-1] + [{**TOOL_DEFINITIONS[-1], "cache_control": {"type": "ephemeral"}}]


def run_agent(task: str, history: list) -> list:
    history.append({"role": "user", "content": task})
    if len(history) > _HIST_TRIM:
        history = history[-_HIST_TRIM:]

    _, history = _get_router().agent_run(
        system        = SYSTEM_PROMPT,
        messages      = history,
        tools         = TOOL_DEFINITIONS,
        tool_executor = execute_tool,
    )
    return history
