"""
Git router — exposes workspace git operations as REST endpoints.
All commands run in WORKSPACE_ROOT.
"""
import subprocess
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/git", tags=["git"])

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # myworkspace/

BLOCKED = ["rm -rf /", "push --force", "reset --hard origin", "clean -fd"]


def _git(*args, timeout: int = 30) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(WORKSPACE_ROOT),
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


# ── Status / info ─────────────────────────────────────────────────────────────

@router.get("/status")
def git_status():
    rc,  status, _   = _git("status", "--short", "--branch")
    rc2, log,    _   = _git("log", "--oneline", "-25", "--decorate")
    rc3, staged, _   = _git("diff", "--cached", "--stat")
    rc4, unstaged, _ = _git("diff", "--stat")
    rc5, branch, _   = _git("branch", "--show-current")
    rc6, remote, _   = _git("remote", "-v")

    lines      = status.splitlines() if status else []
    branch_line = lines[0] if lines else ""
    file_lines  = lines[1:] if len(lines) > 1 else []

    files = []
    for line in file_lines:
        if len(line) >= 3:
            xy   = line[:2]
            path = line[3:].strip()
            st   = "staged"   if xy[0] not in (" ", "?") else \
                   "untracked" if xy == "??" else "modified"
            files.append({"status": xy.strip(), "path": path, "state": st})

    return {
        "branch":       branch.strip(),
        "branch_line":  branch_line,
        "files":        files,
        "log":          log,
        "staged_stat":  staged,
        "unstaged_stat": unstaged,
        "has_remote":   bool(remote),
    }


@router.get("/diff")
def git_diff(staged: bool = False):
    if staged:
        rc, out, err = _git("diff", "--cached")
    else:
        rc, out, err = _git("diff")
    return {"diff": (out or err)[:12000]}


# ── Mutations ─────────────────────────────────────────────────────────────────

class AddBody(BaseModel):
    files: list[str] = []   # empty → stage all tracked changes


class CommitBody(BaseModel):
    message: str
    files:   list[str] = []  # empty → commit already-staged


class PushBody(BaseModel):
    remote: str = "origin"
    branch: str = ""


@router.post("/add")
def git_add(body: AddBody):
    if body.files:
        rc, out, err = _git("add", "--", *body.files)
    else:
        rc, out, err = _git("add", "-u")   # stage all tracked modifications
    return {"ok": rc == 0, "output": out or err or "staged"}


@router.post("/add-all")
def git_add_all():
    rc, out, err = _git("add", "-A")
    return {"ok": rc == 0, "output": out or err or "all staged"}


@router.post("/unstage")
def git_unstage(body: AddBody):
    if body.files:
        rc, out, err = _git("restore", "--staged", "--", *body.files)
    else:
        rc, out, err = _git("restore", "--staged", ".")
    return {"ok": rc == 0, "output": out or err or "unstaged"}


@router.post("/commit")
def git_commit(body: CommitBody):
    if not body.message.strip():
        return JSONResponse({"ok": False, "output": "Commit message is required"}, status_code=400)
    if body.files:
        _git("add", "--", *body.files)
    rc, out, err = _git("commit", "-m", body.message.strip())
    return {"ok": rc == 0, "output": out or err}


@router.post("/push")
def git_push(body: PushBody):
    args = ["push", body.remote]
    if body.branch:
        args.append(body.branch)
    rc, out, err = _git(*args, timeout=60)
    return {"ok": rc == 0, "output": out or err}


@router.post("/pull")
def git_pull():
    rc, out, err = _git("pull", timeout=60)
    return {"ok": rc == 0, "output": out or err}


@router.post("/discard")
def git_discard(body: AddBody):
    """Discard unstaged changes to specific files."""
    if not body.files:
        return JSONResponse({"ok": False, "output": "Specify files to discard"}, status_code=400)
    rc, out, err = _git("restore", "--", *body.files)
    return {"ok": rc == 0, "output": out or err or "discarded"}
