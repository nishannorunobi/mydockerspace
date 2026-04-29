"""
Tool definitions and executor for the Docker AI agent.
The agent uses these to answer questions and take actions on containers.
"""
import json
from pathlib import Path

import database as db
from monitor import list_containers, get_stats, restart_container, get_logs, STATUS_FILE

TOOL_DEFINITIONS = [
    {
        "name": "list_containers",
        "description": "List all Docker containers (running and stopped) with status, image, and uptime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "running_only": {
                    "type": "boolean",
                    "description": "If true, only return running containers (default false — returns all)"
                }
            }
        }
    },
    {
        "name": "get_container_stats",
        "description": "Get live CPU and memory stats for all currently running containers.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_container_logs",
        "description": "Get recent log output from a specific container.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":  {"type": "string",  "description": "Container name or ID"},
                "lines": {"type": "integer", "description": "Lines to return (default 50, max 200)"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "restart_container",
        "description": "Restart a specific container. Use when it is stopped or unhealthy. Verify it came back up after.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Container name or ID to restart"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "get_events",
        "description": "Query the event database — container stops, restarts, restart failures. Filter by container name optionally.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":          {"type": "integer", "description": "Number of events (default 20)"},
                "container_name": {"type": "string",  "description": "Filter to one container (optional)"}
            }
        }
    },
    {
        "name": "get_container_history",
        "description": "Get snapshot history for a specific container — status, CPU, memory over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":  {"type": "string",  "description": "Container name"},
                "limit": {"type": "integer", "description": "Number of snapshots (default 20)"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "get_current_status",
        "description": "Get the full docker_status.json snapshot — all containers, running/stopped counts, recent events. Always call this first for an overview.",
        "input_schema": {"type": "object", "properties": {}}
    }
]


def execute_tool(name: str, inp: dict) -> dict:

    if name == "list_containers":
        running_only = inp.get("running_only", False)
        containers   = list_containers(all_containers=not running_only)
        return {"containers": containers, "count": len(containers)}

    if name == "get_container_stats":
        return {"stats": get_stats()}

    if name == "get_container_logs":
        lines = min(inp.get("lines", 50), 200)
        return {"name": inp["name"], "logs": get_logs(inp["name"], lines)}

    if name == "restart_container":
        ok, msg = restart_container(inp["name"])
        event   = "manually_restarted" if ok else "manual_restart_failed"
        db.log_event(inp["name"], inp["name"], event, "requested via AI agent")
        return {"success": ok, "message": msg, "container": inp["name"]}

    if name == "get_events":
        return {"events": db.get_events(
            limit=inp.get("limit", 20),
            container_name=inp.get("container_name"),
        )}

    if name == "get_container_history":
        return {"history": db.get_snapshots(
            container_name=inp["name"],
            limit=inp.get("limit", 20),
        )}

    if name == "get_current_status":
        if STATUS_FILE.exists():
            return json.loads(STATUS_FILE.read_text())
        return {"error": "docker_status.json not yet written — monitor may still be starting"}

    return {"error": f"Unknown tool: {name}"}
