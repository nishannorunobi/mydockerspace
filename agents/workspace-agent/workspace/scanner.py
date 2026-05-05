"""
Workspace Scanner — background thread that continuously indexes the workspace.

Every INTERVAL seconds it:
  1. Walks the workspace tree (skipping ignored dirs)
  2. Detects new / modified / deleted files by comparing mtime + hash
  3. Updates the files table and logs changes to file_history
  4. Runs template detection to identify project types
  5. Writes a human-readable summary to memory/scan_status.md
"""
import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import db

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent

IGNORE = {
    ".git", ".venv", "__pycache__", "node_modules", "target",
    ".mvn", ".claude", "build", "dist", ".next", ".nuxt",
    "vscode-server-extensions", "mountspace",
}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB — skip hashing large files

# ── Template fingerprints ──────────────────────────────────────────────────────
# A template matches when ALL required files exist relative to root_path

TEMPLATE_PATTERNS = [
    {
        "type":     "python-http-agent",
        "required": ["server.py", "requirements.txt", "start.sh"],
        "optional": ["stop.sh", "health.sh", "agent.py", "tools.py", "database.py", "db.py"],
        "name_fn":  lambda p: f"{Path(p).parent.name} / {Path(p).name}",
    },
    {
        "type":     "docker-compose-project",
        "required": ["docker-compose.yml"],
        "optional": ["Dockerfile", ".env.example", "Makefile"],
        "name_fn":  lambda p: Path(p).name,
    },
    {
        "type":     "spring-boot-maven",
        "required": ["pom.xml"],
        "optional": ["src/main/java", "src/main/resources/application.properties"],
        "name_fn":  lambda p: Path(p).name,
    },
    {
        "type":     "docker-host-project",
        "required": ["dockerspace/host_scripts/docker-compose.yml"],
        "optional": ["dockerspace/container_scripts", "dockerspace/host_scripts/Makefile"],
        "name_fn":  lambda p: Path(p).name,
    },
    {
        "type":     "scripted-service",
        "required": ["start.sh", "stop.sh", "health.sh"],
        "optional": ["build.sh"],
        "name_fn":  lambda p: Path(p).name,
    },
    {
        "type":     "nodejs-project",
        "required": ["package.json"],
        "optional": ["src", "index.js", "index.ts", "vite.config.ts"],
        "name_fn":  lambda p: Path(p).name,
    },
]

_STATUS_FILE = Path(__file__).resolve().parent / "memory" / "scan_status.md"
_TODAY_FILE  = Path(__file__).resolve().parent / "memory" / "today.json"


def _sha1(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return f"large:{path.stat().st_size}"
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _walk(root: Path) -> list[Path]:
    """Yield all files and dirs under root, skipping IGNORE dirs."""
    result = []
    try:
        for entry in os.scandir(root):
            if entry.name in IGNORE or entry.name.startswith("."):
                continue
            p = Path(entry.path)
            result.append(p)
            if entry.is_dir(follow_symlinks=False):
                result.extend(_walk(p))
    except PermissionError:
        pass
    return result


def _detect_templates(root: Path):
    """Walk every directory; if it matches a template pattern, upsert it."""
    try:
        all_dirs = [d for d in _walk(root) if d.is_dir()]
        all_dirs.insert(0, root)
        for d in all_dirs:
            rel = str(d.relative_to(root))
            for pat in TEMPLATE_PATTERNS:
                if all((d / req).exists() for req in pat["required"]):
                    present  = [f for f in pat["required"] + pat["optional"] if (d / f).exists()]
                    name     = pat["name_fn"](rel) if rel != "." else "workspace root"
                    db.upsert_template(
                        name        = str(name),
                        project_type= pat["type"],
                        root_path   = rel,
                        key_files   = present,
                        conventions = {},
                    )
                    break  # one template per directory
    except Exception:
        pass


def _build_suggestions(changed: int, deleted: int) -> list[dict]:
    """
    Rule-based suggestion engine — runs every scan, zero LLM cost.
    Returns list of {level, message, source} sorted by severity.
    """
    suggestions = []

    def _add(level, message, source):
        suggestions.append({"level": level, "message": message,
                             "source": source, "ts": datetime.now().isoformat(timespec="seconds")})

    # ── Emergency: mass deletion ───────────────────────────────────────────
    if deleted >= 10:
        _add("emergency", f"{deleted} files deleted in one scan — verify this is intentional", "file-watch")

    # ── Emergency: .env or secrets in recent changes ───────────────────────
    recent = db.get_recent_changes(30)
    secret_paths = [c["path"] for c in recent if
                    any(s in c["path"].lower() for s in (".env", "secret", "credential", "password", "private_key"))
                    and c["event"] in ("created", "modified")]
    if secret_paths:
        _add("emergency", f"Sensitive file changed: {secret_paths[0]}", "security")

    # ── Warning: urgent todos ──────────────────────────────────────────────
    try:
        todos    = db.get_todos("open")
        urgent   = [t for t in todos if t["priority"] == "urgent"]
        high     = [t for t in todos if t["priority"] == "high"]
        if urgent:
            _add("warning", f"{len(urgent)} URGENT task(s) — '{urgent[0]['text'][:60]}'", "todos")
        elif high:
            _add("info", f"{len(high)} high-priority task(s) open", "todos")
        elif len(todos) > 5:
            _add("info", f"{len(todos)} open tasks in the queue", "todos")
    except Exception:
        pass

    # ── Warning: many file changes ─────────────────────────────────────────
    if changed >= 20:
        _add("warning", f"{changed} files changed this scan — consider a git commit", "file-watch")
    elif changed >= 5:
        _add("info", f"{changed} files modified recently", "file-watch")

    # ── Info: Dockerfile or compose changed ───────────────────────────────
    docker_changed = [c for c in recent[:10] if
                      any(s in c["path"] for s in ("Dockerfile", "docker-compose", "compose.yml"))
                      and c["event"] == "modified"]
    if docker_changed:
        _add("info", f"Docker config changed: {docker_changed[0]['path'].split('/')[-1]} — ↺ Rebuild may be needed", "docker")

    # ── Info: knowledge base empty ────────────────────────────────────────
    try:
        if not db.get_knowledge():
            _add("info", "Knowledge base is empty — chat with workspace agent to start building memory", "knowledge")
    except Exception:
        pass

    # Sort: emergency → warning → info
    order = {"emergency": 0, "warning": 1, "info": 2}
    suggestions.sort(key=lambda s: order.get(s["level"], 9))
    return suggestions


def _write_today():
    """Write today.json — the dashboard Today panel reads this."""
    try:
        today = {
            "generated_at":     datetime.now().isoformat(timespec="seconds"),
            "todos":            db.get_todos(status="open"),
            "recent_changes":   db.get_recent_changes(15),
            "templates":        db.get_templates(),
            "scan_stats":       db.count_files(),
            "last_scan":        db.get_last_scan(),
            "recent_knowledge": db.get_knowledge()[:10],
            "prompt_history":   db.get_prompt_history(5),
            "suggestions":      [],   # filled by _build_suggestions each scan
        }
        _TODAY_FILE.parent.mkdir(exist_ok=True)
        _TODAY_FILE.write_text(json.dumps(today, indent=2))
    except Exception:
        pass


def update_today_suggestions(suggestions: list):
    """Merge suggestion list into the existing today.json without full re-read."""
    try:
        if _TODAY_FILE.exists():
            data = json.loads(_TODAY_FILE.read_text())
        else:
            data = {}
        data["suggestions"]        = suggestions
        data["suggestions_updated"] = datetime.now().isoformat(timespec="seconds")
        _TODAY_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def _write_status(indexed: int, changed: int, deleted: int, elapsed: float):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats = db.count_files()
    last  = db.get_last_scan()
    lines = [
        f"# Workspace Scanner — Status",
        f"",
        f"**Last scan:** {ts}  ({elapsed:.1f}s)",
        f"**Files indexed:** {stats['files']}  |  **Dirs:** {stats['dirs']}",
        f"**Changes this scan:** +{changed} modified / -{deleted} deleted",
        f"**Total history events:** {stats['history_events']}",
        f"",
        f"## Recent changes",
    ]
    for ev in db.get_recent_changes(10):
        lines.append(f"- `{ev['event'].upper()}` {ev['path']}  _{ev['timestamp']}_")
    lines += ["", "## Detected project templates"]
    for t in db.get_templates():
        lines.append(f"- **{t['project_type']}** → `{t['root_path']}` ({', '.join(t['key_files'][:3])}...)")
    try:
        _STATUS_FILE.parent.mkdir(exist_ok=True)
        _STATUS_FILE.write_text("\n".join(lines))
    except Exception:
        pass


class WorkspaceScanner(threading.Thread):
    INTERVAL = 30  # seconds between scans

    def __init__(self, on_change: Optional[Callable] = None):
        super().__init__(daemon=True)
        self._stop      = threading.Event()
        self._on_change = on_change
        self._known_mtimes: dict[str, float] = {}

    def stop(self):
        self._stop.set()

    def run(self):
        db.init()
        self._full_scan()             # initial scan on startup
        while not self._stop.wait(self.INTERVAL):
            self._full_scan()

    def _full_scan(self):
        import time
        t0 = time.monotonic()
        scan_id = db.start_scan()
        indexed = changed = deleted = 0

        try:
            root     = WORKSPACE_ROOT
            on_disk  = set()
            all_paths = _walk(root)

            for p in all_paths:
                rel = str(p.relative_to(root))
                on_disk.add(rel)
                try:
                    st    = p.stat()
                    mtime = st.st_mtime
                    size  = st.st_size if p.is_file() else 0
                    ftype = "file" if p.is_file() else "dir"

                    prev_mtime = self._known_mtimes.get(rel)
                    if prev_mtime is None or mtime != prev_mtime:
                        fhash = _sha1(p) if ftype == "file" else ""
                        db.upsert_file(rel, ftype, size, fhash, mtime)
                        if prev_mtime is not None:
                            changed += 1
                        self._known_mtimes[rel] = mtime

                    indexed += 1
                except Exception:
                    pass

            # Detect deletions
            in_db = {r["path"] for r in db.get_files()}
            for gone in in_db - on_disk:
                db.mark_deleted(gone)
                self._known_mtimes.pop(gone, None)
                deleted += 1

            _detect_templates(root)

        finally:
            elapsed = time.monotonic() - t0
            db.finish_scan(scan_id, indexed, changed, deleted)
            suggestions = _build_suggestions(changed, deleted)
            _write_status(indexed, changed, deleted, elapsed)
            _write_today()
            update_today_suggestions(suggestions)
            if (changed or deleted) and self._on_change:
                self._on_change(changed, deleted)
