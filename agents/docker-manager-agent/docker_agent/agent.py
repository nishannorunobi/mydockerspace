"""
Docker AI agent — given a natural language task, reasons over Docker state
using tools and returns a text response.
Called by the /api/tasks endpoint so the agent-orchestrator can dispatch here.
"""
import json
import os

import anthropic
from tools import TOOL_DEFINITIONS, execute_tool

SYSTEM_PROMPT = """You are a Docker Orchestrator Agent.

Your responsibilities:
- Report the health and status of all Docker containers on this system
- Diagnose why a container stopped (read its logs, check events)
- Restart stopped containers and confirm they came back up
- Summarise recent events from the database

Rules:
- Always call get_current_status first to get a quick overview
- If asked about a specific container, use get_container_logs and get_events filtered by name
- After restarting a container, call list_containers to verify it is running again
- Be concise: container name, action taken, result — no waffle
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
