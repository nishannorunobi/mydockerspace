"""
Console router — run shell commands from the dashboard.
Commands run in WORKSPACE_ROOT (or a sub-path the user specifies).
"""
import subprocess
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/console", tags=["console"])

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # myworkspace/

BLOCKED = [
    "rm -rf /", "mkfs", ":(){:|:&};:", "> /dev/sd",
    "dd if=/dev/zero", "chmod -R 777 /", "chown -R",
]


class CmdBody(BaseModel):
    command: str
    cwd: str = ""   # relative to workspace root; empty = workspace root


@router.post("/exec")
def exec_command(body: CmdBody):
    cmd = body.command.strip()
    if not cmd:
        return JSONResponse({"ok": False, "output": "No command"}, status_code=400)

    for b in BLOCKED:
        if b in cmd:
            return {"ok": False, "output": f"Blocked for safety: {b}", "exit_code": 1}

    if body.cwd:
        cwd = (WORKSPACE_ROOT / body.cwd).resolve()
        if not str(cwd).startswith(str(WORKSPACE_ROOT)):
            return {"ok": False, "output": "cwd must be inside workspace", "exit_code": 1}
        if not cwd.exists():
            return {"ok": False, "output": f"Directory not found: {body.cwd}", "exit_code": 1}
    else:
        cwd = WORKSPACE_ROOT

    try:
        r = subprocess.run(
            cmd, shell=True, cwd=str(cwd),
            capture_output=True, text=True, timeout=60,
        )
        output = (r.stdout + r.stderr)
        return {
            "ok":       r.returncode == 0,
            "output":   output[:10000],
            "exit_code": r.returncode,
            "cwd":      str(cwd.relative_to(WORKSPACE_ROOT)) or ".",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "Command timed out after 60s", "exit_code": 124}
    except Exception as e:
        return {"ok": False, "output": str(e), "exit_code": 1}


@router.get("/cwd-list")
def list_cwd():
    """Return top-level project directories for the CWD selector."""
    dirs = []
    for p in sorted(WORKSPACE_ROOT.iterdir()):
        if p.is_dir() and not p.name.startswith(".") and p.name not in ("__pycache__",):
            dirs.append(p.name)
            for sub in sorted(p.iterdir()):
                if sub.is_dir() and not sub.name.startswith("."):
                    dirs.append(f"{p.name}/{sub.name}")
    return {"dirs": dirs[:80]}
