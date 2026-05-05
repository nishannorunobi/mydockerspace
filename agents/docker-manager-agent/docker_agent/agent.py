"""
Docker AI agent — given a natural language task, reasons over Docker state
using tools and returns a text response.
Called by the /api/tasks endpoint so the agent-orchestrator can dispatch here.
"""
import json
import os

import anthropic
from tools import TOOL_DEFINITIONS, execute_tool

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


def run_agent(task: str, history: list) -> list:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history.append({"role": "user", "content": task})

    while True:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=history,
        )
        tool_calls  = [b for b in resp.content if b.type == "tool_use"]
        text_blocks = [b for b in resp.content if b.type == "text"]

        if resp.stop_reason == "end_turn" or not tool_calls:
            final = " ".join(b.text for b in text_blocks).strip()
            if final:
                history.append({"role": "assistant", "content": final})
            break

        history.append({"role": "assistant", "content": resp.content})
        results = []
        for b in tool_calls:
            result = execute_tool(b.name, b.input)
            results.append({
                "type":        "tool_result",
                "tool_use_id": b.id,
                "content":     json.dumps(result),
            })
        history.append({"role": "user", "content": results})

    return history
