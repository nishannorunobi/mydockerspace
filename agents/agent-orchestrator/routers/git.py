"""
Git router — exposes workspace git operations as REST endpoints.
Each endpoint accepts ?repo=<relative-path> to target any git repo
under WORKSPACE_ROOT. Defaults to WORKSPACE_ROOT itself.
"""
import subprocess
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/git", tags=["git"])

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # myworkspace/
PROJECT_SPACE  = WORKSPACE_ROOT / "projectspace"

BLOCKED = ["push --force", "reset --hard origin", "clean -fd"]


def _resolve_repo(repo: str) -> tuple[Path, str | None]:
    """
    Resolve repo relative path → absolute Path.
    Returns (path, error_message). error_message is None on success.
    """
    if not repo:
        return WORKSPACE_ROOT, None
    candidate = (WORKSPACE_ROOT / repo).resolve()
    if not str(candidate).startswith(str(WORKSPACE_ROOT)):
        return WORKSPACE_ROOT, "repo path must be inside workspace"
    if not (candidate / ".git").exists():
        return WORKSPACE_ROOT, f"not a git repo: {repo}"
    return candidate, None


def _git(*args, cwd: Path = WORKSPACE_ROOT, timeout: int = 30) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


# ── Repo discovery ────────────────────────────────────────────────────────────

@router.get("/repos")
def list_repos():
    """Discover git repositories: root workspace first, then all repos under projectspace/."""

    def _repo_info(cwd: Path, path_str: str, name: str) -> dict:
        _, br, _  = _git("branch", "--show-current", cwd=cwd)
        _, st, _  = _git("status", "--short", cwd=cwd)
        _, rm, _  = _git("remote", "-v", cwd=cwd)
        ch        = len([l for l in st.splitlines() if l.strip()])
        has_remote = bool(rm.strip())
        branch_name = br.strip() or "?"

        # ahead/behind: try @{u} first, then origin/<branch>
        _, a_raw, _ = _git("rev-list", "@{u}..HEAD", "--count", cwd=cwd)
        _, b_raw, _ = _git("rev-list", "HEAD..@{u}", "--count", cwd=cwd)
        ahead  = int(a_raw.strip()) if a_raw.strip().isdigit() else None
        behind = int(b_raw.strip()) if b_raw.strip().isdigit() else None
        if ahead is None and has_remote and branch_name not in ("?", ""):
            _, a2, _ = _git("rev-list", f"origin/{branch_name}..HEAD", "--count", cwd=cwd)
            _, b2, _ = _git("rev-list", f"HEAD..origin/{branch_name}", "--count", cwd=cwd)
            ahead  = int(a2.strip()) if a2.strip().isdigit() else 0
            behind = int(b2.strip()) if b2.strip().isdigit() else 0
        if ahead is None:
            ahead = behind = 0

        return {
            "path":       path_str,
            "name":       name,
            "branch":     branch_name,
            "changed":    ch,
            "ahead":      ahead,
            "behind":     behind,
            "has_remote": has_remote,
        }

    repos = [_repo_info(WORKSPACE_ROOT, "", "myworkspace (root)")]

    if PROJECT_SPACE.exists():
        for p in sorted(PROJECT_SPACE.rglob(".git")):
            if p.is_dir():
                repo_path = p.parent
                rel = repo_path.relative_to(WORKSPACE_ROOT)
                if len(rel.parts) <= 3:
                    try:
                        repos.append(_repo_info(repo_path, str(rel), repo_path.name))
                    except Exception:
                        repos.append({"path": str(rel), "name": repo_path.name,
                                      "branch": "?", "changed": 0, "ahead": 0, "behind": 0, "has_remote": False})
    return {"repos": repos}


# ── Status / info ─────────────────────────────────────────────────────────────

@router.get("/status")
def git_status(repo: str = Query(default="")):
    cwd, err = _resolve_repo(repo)
    if err:
        return JSONResponse({"error": err}, status_code=400)

    rc,  status, _   = _git("status", "--short", "--branch", cwd=cwd)
    rc2, log,    _   = _git("log", "--oneline", "-25", "--decorate", cwd=cwd)
    rc3, staged, _   = _git("diff", "--cached", "--stat", cwd=cwd)
    rc4, unstaged, _ = _git("diff", "--stat", cwd=cwd)
    rc5, branch, _   = _git("branch", "--show-current", cwd=cwd)
    rc6, remote, _   = _git("remote", "-v", cwd=cwd)
    has_remote = bool(remote.strip())

    # Try tracking branch first (@{u}), fall back to origin/<branch>
    branch_name = branch.strip()
    _, ahead_raw,  _ = _git("rev-list", "@{u}..HEAD",  "--count", cwd=cwd)
    _, behind_raw, _ = _git("rev-list", "HEAD..@{u}",  "--count", cwd=cwd)
    ahead  = int(ahead_raw.strip())  if ahead_raw.strip().isdigit()  else None
    behind = int(behind_raw.strip()) if behind_raw.strip().isdigit() else None

    if ahead is None and has_remote and branch_name:
        _, a2, _ = _git("rev-list", f"origin/{branch_name}..HEAD", "--count", cwd=cwd)
        _, b2, _ = _git("rev-list", f"HEAD..origin/{branch_name}", "--count", cwd=cwd)
        ahead  = int(a2.strip()) if a2.strip().isdigit() else 0
        behind = int(b2.strip()) if b2.strip().isdigit() else 0

    if ahead is None:
        ahead  = 0
        behind = 0

    lines       = status.splitlines() if status else []
    branch_line = lines[0] if lines else ""
    file_lines  = lines[1:] if len(lines) > 1 else []

    files = []
    for line in file_lines:
        if len(line) >= 3:
            xy   = line[:2]
            path = line[3:].strip()
            st   = "staged"    if xy[0] not in (" ", "?") else \
                   "untracked" if xy == "??" else "modified"
            # Resolve rename "old -> new" — take the destination
            display_path = path.split(" -> ")[-1].strip() if " -> " in path else path
            abs_path = cwd / display_path
            try:
                sz = abs_path.stat().st_size
                if sz >= 1_048_576:
                    size_str = f"{sz / 1_048_576:.1f} MB"
                elif sz >= 1024:
                    size_str = f"{sz / 1024:.1f} KB"
                else:
                    size_str = f"{sz} B"
            except OSError:
                sz = 0
                size_str = "—"
            files.append({"status": xy.strip(), "path": path, "state": st,
                          "size": size_str, "size_bytes": sz})

    return {
        "branch":        branch.strip(),
        "branch_line":   branch_line,
        "files":         files,
        "log":           log,
        "staged_stat":   staged,
        "unstaged_stat": unstaged,
        "has_remote":    has_remote,
        "ahead":         ahead,
        "behind":        behind,
        "repo":          repo or ".",
    }


@router.get("/diff")
def git_diff(staged: bool = False, repo: str = Query(default="")):
    cwd, err = _resolve_repo(repo)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    if staged:
        rc, out, err2 = _git("diff", "--cached", cwd=cwd)
    else:
        rc, out, err2 = _git("diff", cwd=cwd)
    return {"diff": (out or err2)[:12000]}


# ── Mutations ─────────────────────────────────────────────────────────────────

class AddBody(BaseModel):
    files: list[str] = []
    repo:  str       = ""


class CommitBody(BaseModel):
    message: str
    files:   list[str] = []
    repo:    str       = ""


class PushBody(BaseModel):
    remote: str = "origin"
    branch: str = ""
    repo:   str = ""


class RepoBody(BaseModel):
    repo: str = ""


@router.post("/add")
def git_add(body: AddBody):
    cwd, err = _resolve_repo(body.repo)
    if err:
        return {"ok": False, "output": err}
    if body.files:
        rc, out, err2 = _git("add", "--", *body.files, cwd=cwd)
    else:
        rc, out, err2 = _git("add", "-u", cwd=cwd)
    return {"ok": rc == 0, "output": out or err2 or "staged"}


@router.post("/add-all")
def git_add_all(body: RepoBody = RepoBody()):
    cwd, err = _resolve_repo(body.repo)
    if err:
        return {"ok": False, "output": err}
    rc, out, err2 = _git("add", "-A", cwd=cwd)
    return {"ok": rc == 0, "output": out or err2 or "all staged"}


@router.post("/unstage")
def git_unstage(body: AddBody):
    cwd, err = _resolve_repo(body.repo)
    if err:
        return {"ok": False, "output": err}
    if body.files:
        rc, out, err2 = _git("restore", "--staged", "--", *body.files, cwd=cwd)
    else:
        rc, out, err2 = _git("restore", "--staged", ".", cwd=cwd)
    return {"ok": rc == 0, "output": out or err2 or "unstaged"}


@router.post("/commit")
def git_commit(body: CommitBody):
    if not body.message.strip():
        return JSONResponse({"ok": False, "output": "Commit message is required"}, status_code=400)
    cwd, err = _resolve_repo(body.repo)
    if err:
        return {"ok": False, "output": err}
    if body.files:
        _git("add", "--", *body.files, cwd=cwd)
    rc, out, err2 = _git("commit", "-m", body.message.strip(), cwd=cwd)
    return {"ok": rc == 0, "output": out or err2}


@router.post("/push")
def git_push(body: PushBody):
    cwd, err = _resolve_repo(body.repo)
    if err:
        return {"ok": False, "output": err}
    args = ["push", body.remote]
    if body.branch:
        args.append(body.branch)
    rc, out, err2 = _git(*args, cwd=cwd, timeout=60)
    return {"ok": rc == 0, "output": out or err2}


@router.post("/pull")
def git_pull(body: RepoBody = RepoBody()):
    cwd, err = _resolve_repo(body.repo)
    if err:
        return {"ok": False, "output": err}
    rc, out, err2 = _git("pull", cwd=cwd, timeout=60)
    return {"ok": rc == 0, "output": out or err2}


@router.post("/discard")
def git_discard(body: AddBody):
    """Discard unstaged changes to specific files."""
    if not body.files:
        return JSONResponse({"ok": False, "output": "Specify files to discard"}, status_code=400)
    cwd, err = _resolve_repo(body.repo)
    if err:
        return {"ok": False, "output": err}
    rc, out, err2 = _git("restore", "--", *body.files, cwd=cwd)
    return {"ok": rc == 0, "output": out or err2 or "discarded"}
