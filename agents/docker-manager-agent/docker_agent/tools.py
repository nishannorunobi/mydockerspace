"""
Tool definitions and executor for the Docker AI agent.
The agent uses these to answer questions and take actions on containers.
"""
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import database as db
from monitor import list_containers, get_stats, restart_container, start_container, stop_container, get_logs, STATUS_FILE

DB_AGENT_CONTAINER = "mypostgresql_db-container"
DB_AGENT_PORT      = 8890
DB_AGENT_NETWORK   = "ums-network"


def _db_agent_url() -> tuple[str | None, str | None]:
    """Return (url, error) for the db-agent running inside the DB container."""
    try:
        r = subprocess.run(
            ["docker", "inspect", DB_AGENT_CONTAINER, "--format", "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None, f"{DB_AGENT_CONTAINER} not found or not running"
        networks = json.loads(r.stdout.strip())
        ip = (networks.get(DB_AGENT_NETWORK) or {}).get("IPAddress", "")
        if not ip:
            return None, f"{DB_AGENT_CONTAINER} is not on {DB_AGENT_NETWORK}"
        return f"http://{ip}:{DB_AGENT_PORT}", None
    except Exception as e:
        return None, str(e)


def _db_agent_get(path: str) -> dict:
    url, err = _db_agent_url()
    if err:
        return {"error": err}
    try:
        with urllib.request.urlopen(f"{url}{path}", timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": f"db-agent GET {path}: {e}"}


def _db_agent_post(path: str, payload: dict | None = None) -> dict:
    url, err = _db_agent_url()
    if err:
        return {"error": err}
    data = json.dumps(payload or {}).encode()
    req  = urllib.request.Request(
        f"{url}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return json.loads(body)
        except Exception:
            return {"error": f"HTTP {e.code}: {body[:300]}"}
    except Exception as e:
        return {"error": f"db-agent POST {path}: {e}"}

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
        "name": "start_container",
        "description": "Start a stopped container. Use when the container is stopped and needs to be brought up.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Container name or ID to start"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "stop_container",
        "description": "Stop a running container gracefully.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Container name or ID to stop"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "restart_container",
        "description": "Restart a running container (stop then start). Use when the container is unhealthy or needs a fresh restart.",
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
    },
    {
        "name": "db_agent_status",
        "description": (
            "Check whether the DB agent is reachable inside mypostgresql_db-container "
            "and whether PostgreSQL is running. Call this before any DB start/stop action."
        ),
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "db_start",
        "description": (
            "Tell the DB agent to start PostgreSQL inside mypostgresql_db-container. "
            "The DB agent runs startdb.sh --prepare-only which initialises the cluster, "
            "creates the umsdb database, and applies tables + seed data if needed."
        ),
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "db_stop",
        "description": "Tell the DB agent to stop PostgreSQL inside mypostgresql_db-container gracefully.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "db_agent_task",
        "description": (
            "Send a natural-language task to the DB agent AI running inside "
            "mypostgresql_db-container. The DB agent can run SQL, check connections, "
            "inspect schema, read logs, and update its memory. "
            "Use for anything DB-related that goes beyond start/stop."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task description for the DB agent"}
            },
            "required": ["task"]
        }
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

    if name == "start_container":
        ok, msg = start_container(inp["name"])
        event   = "manually_started" if ok else "manual_start_failed"
        db.log_event(inp["name"], inp["name"], event, "requested via AI agent")
        return {"success": ok, "message": msg, "container": inp["name"]}

    if name == "stop_container":
        ok, msg = stop_container(inp["name"])
        event   = "manually_stopped" if ok else "manual_stop_failed"
        db.log_event(inp["name"], inp["name"], event, "requested via AI agent")
        return {"success": ok, "message": msg, "container": inp["name"]}

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

    if name == "db_agent_status":
        return _db_agent_get("/health")

    if name == "db_start":
        return _db_agent_post("/api/db/start")

    if name == "db_stop":
        return _db_agent_post("/api/db/stop")

    if name == "db_agent_task":
        return _db_agent_post("/api/tasks", {"task": inp.get("task", "")})

    return {"error": f"Unknown tool: {name}"}
