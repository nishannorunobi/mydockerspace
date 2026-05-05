"""
Config router — manage shared settings (e.g. Anthropic API key) via REST.

POST /api/config/anthropic-key   {"key": "sk-ant-..."}
  → writes to agents/shared.conf and db-agent/agent.conf,
    updates the live process env, then restarts docker-manager-agent
    and the db-agent inside the container so all agents pick up the new key.

GET /api/config/anthropic-key
  → returns {"set": true, "masked": "sk-ant-api03-...xxxx"} (never the raw key)
"""
import os
import re
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/config", tags=["config"])

# Paths that store the key
_BASE        = Path(__file__).resolve().parent.parent          # agent-orchestrator/
_SHARED_CONF = _BASE.parent / "shared.conf"                    # agents/shared.conf

_KEY_RE      = re.compile(r"^(ANTHROPIC_API_KEY\s*=).*", re.MULTILINE)


def _mask(key: str) -> str:
    if len(key) <= 20:
        return "***"
    return key[:15] + "..." + key[-4:]


_DB_CONTAINER   = "mypostgresql_db-container"
_DB_CONF_INSIDE = "/mypostgresql_db/db-agent/agent.conf"


def _update_conf(path: Path, key: str):
    """Replace or append ANTHROPIC_API_KEY in a .env-style conf file."""
    if not path.exists():
        return
    text = path.read_text()
    new_line = f"ANTHROPIC_API_KEY={key}"
    if _KEY_RE.search(text):
        text = _KEY_RE.sub(new_line, text)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    path.write_text(text)


def _update_db_conf_via_docker(key: str) -> str | None:
    """Update db-agent/agent.conf inside the container via docker exec (root can write it)."""
    script = (
        f"python3 -c \""
        f"import re, pathlib; "
        f"p = pathlib.Path('{_DB_CONF_INSIDE}'); "
        f"t = p.read_text(); "
        f"new = 'ANTHROPIC_API_KEY={key}'; "
        f"t = re.sub(r'^ANTHROPIC_API_KEY.*', new, t, flags=re.MULTILINE) "
        f"    if re.search(r'^ANTHROPIC_API_KEY', t, re.MULTILINE) "
        f"    else t.rstrip() + chr(10) + new + chr(10); "
        f"p.write_text(t)"
        f"\""
    )
    try:
        r = subprocess.run(
            ["docker", "exec", _DB_CONTAINER, "bash", "-c", script],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return (r.stdout + r.stderr).strip() or "docker exec failed"
        return None
    except Exception as e:
        return str(e)


def _restart_docker_agent():
    """Stop and re-start docker-manager-agent (picks up new shared.conf)."""
    home = _BASE.parent / "docker-manager-agent"
    try:
        subprocess.run(["bash", "stop.sh"],  cwd=home, capture_output=True, timeout=15)
        subprocess.Popen(
            ["bash", "start.sh"], cwd=home,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception:
        pass


def _restart_db_agent():
    """Kill and re-launch db-agent uvicorn inside the container."""
    try:
        subprocess.run(
            ["docker", "exec", "mypostgresql_db-container",
             "bash", "-c",
             "pkill -f 'uvicorn server:app' 2>/dev/null || true; "
             "pkill -f 'db-agent/server.py' 2>/dev/null || true"],
            capture_output=True, timeout=10,
        )
        subprocess.Popen(
            ["docker", "exec", "-d", "mypostgresql_db-container",
             "bash", "-c",
             "cd /mypostgresql_db/db-agent && nohup bash start.sh > memory/server.log 2>&1 &"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ── GET ────────────────────────────────────────────────────────────────────────

@router.get("/anthropic-key")
def get_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key and _SHARED_CONF.exists():
        for line in _SHARED_CONF.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    return {
        "set":    bool(key),
        "masked": _mask(key) if key else None,
    }


# ── POST ───────────────────────────────────────────────────────────────────────

class KeyBody(BaseModel):
    key: str


@router.post("/anthropic-key")
def set_key(body: KeyBody):
    raw = body.key.strip()
    if not raw:
        return JSONResponse({"error": "key must not be empty"}, status_code=400)
    if not raw.startswith("sk-ant-"):
        return JSONResponse({"error": "key must start with sk-ant-"}, status_code=400)

    updated = []
    errors  = []

    # shared.conf — writable by the current user
    try:
        _update_conf(_SHARED_CONF, raw)
        updated.append(str(_SHARED_CONF))
    except Exception as e:
        errors.append(f"shared.conf: {e}")

    # db-agent/agent.conf — owned by root (bind-mounted), update via docker exec
    err = _update_db_conf_via_docker(raw)
    if err:
        errors.append(f"db-agent/agent.conf (docker): {err}")
    else:
        updated.append(f"{_DB_CONTAINER}:{_DB_CONF_INSIDE}")

    # Apply to the running process immediately
    os.environ["ANTHROPIC_API_KEY"] = raw

    # Restart affected agents in background so the endpoint returns quickly
    threading.Thread(target=_restart_docker_agent, daemon=True).start()
    threading.Thread(target=_restart_db_agent,     daemon=True).start()

    return {
        "ok":      not errors,
        "masked":  _mask(raw),
        "updated": updated,
        "errors":  errors,
        "note":    "docker-manager-agent and db-agent are restarting to pick up the new key",
    }
