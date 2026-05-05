"""
Workspace persistent database — SQLite, lives in workspace/memory/workspace.db.

Tables:
  files         — current state of every indexed file/dir
  file_history  — every detected change (created / modified / deleted)
  templates     — auto-detected project patterns (python-agent, docker-project, ...)
  knowledge     — LLM-written notes: conventions, rules, anomalies, patterns
  scans         — scan run metadata
"""
import hashlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

_MEMORY  = Path(__file__).resolve().parent / "memory"
DB_PATH  = _MEMORY / "workspace.db"
_lock    = threading.Lock()


# ── bootstrap ─────────────────────────────────────────────────────────────────

def init():
    _MEMORY.mkdir(exist_ok=True)
    with _connect() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                path        TEXT PRIMARY KEY,
                type        TEXT NOT NULL,
                size        INTEGER DEFAULT 0,
                hash        TEXT,
                mtime       REAL,
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS file_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                path        TEXT NOT NULL,
                event       TEXT NOT NULL,
                old_hash    TEXT,
                new_hash    TEXT,
                size_bytes  INTEGER
            );
            CREATE TABLE IF NOT EXISTS templates (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                project_type TEXT NOT NULL,
                root_path    TEXT NOT NULL UNIQUE,
                key_files    TEXT NOT NULL,
                conventions  TEXT,
                detected_at  TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT NOT NULL,
                title       TEXT NOT NULL,
                body        TEXT NOT NULL,
                source_path TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scans (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at      TEXT NOT NULL,
                finished_at     TEXT,
                files_indexed   INTEGER DEFAULT 0,
                files_changed   INTEGER DEFAULT 0,
                files_deleted   INTEGER DEFAULT 0,
                status          TEXT DEFAULT 'running'
            );
            CREATE TABLE IF NOT EXISTS todos (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT NOT NULL,
                priority   TEXT DEFAULT 'normal',
                status     TEXT DEFAULT 'open',
                due_date   TEXT,
                created_at TEXT NOT NULL,
                done_at    TEXT,
                source     TEXT DEFAULT 'manual'
            );
            CREATE TABLE IF NOT EXISTS prompt_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT NOT NULL,
                prompt     TEXT NOT NULL,
                response   TEXT,
                session_id TEXT,
                agent      TEXT DEFAULT 'workspace'
            );
            CREATE INDEX IF NOT EXISTS idx_fh_path   ON file_history (path);
            CREATE INDEX IF NOT EXISTS idx_fh_ts     ON file_history (timestamp);
            CREATE INDEX IF NOT EXISTS idx_tmpl_type ON templates (project_type);
            CREATE INDEX IF NOT EXISTS idx_know_cat  ON knowledge (category);
            CREATE INDEX IF NOT EXISTS idx_todo_stat ON todos (status);
            CREATE INDEX IF NOT EXISTS idx_ph_ts     ON prompt_history (timestamp);
        """)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── files ──────────────────────────────────────────────────────────────────────

def upsert_file(path: str, ftype: str, size: int = 0,
                fhash: str = "", mtime: float = 0.0):
    now = _ts()
    with _lock:
        with _connect() as c:
            existing = c.execute("SELECT hash FROM files WHERE path=?", (path,)).fetchone()
            if existing is None:
                c.execute(
                    "INSERT INTO files (path,type,size,hash,mtime,first_seen,last_seen) VALUES (?,?,?,?,?,?,?)",
                    (path, ftype, size, fhash, mtime, now, now),
                )
                _log_history(c, path, "created", None, fhash, size)
            else:
                old_hash = existing["hash"] or ""
                changed  = fhash and fhash != old_hash
                c.execute(
                    "UPDATE files SET type=?,size=?,hash=?,mtime=?,last_seen=? WHERE path=?",
                    (ftype, size, fhash, mtime, now, path),
                )
                if changed:
                    _log_history(c, path, "modified", old_hash, fhash, size)


def mark_deleted(path: str):
    with _lock:
        with _connect() as c:
            row = c.execute("SELECT hash, size FROM files WHERE path=?", (path,)).fetchone()
            if row:
                _log_history(c, path, "deleted", row["hash"], None, row["size"])
                c.execute("DELETE FROM files WHERE path=?", (path,))


def _log_history(conn, path, event, old_hash, new_hash, size):
    conn.execute(
        "INSERT INTO file_history (timestamp,path,event,old_hash,new_hash,size_bytes) VALUES (?,?,?,?,?,?)",
        (_ts(), path, event, old_hash, new_hash, size),
    )


def get_files(path_like: str = "", ftype: str = "") -> list[dict]:
    with _connect() as c:
        clauses, params = [], []
        if path_like:
            clauses.append("path LIKE ?")
            params.append(f"%{path_like}%")
        if ftype:
            clauses.append("type = ?")
            params.append(ftype)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = c.execute(
            f"SELECT path,type,size,hash,last_seen FROM files {where} ORDER BY path LIMIT 500",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_file_history(path: str, limit: int = 30) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT timestamp,path,event,old_hash,new_hash,size_bytes FROM file_history "
            "WHERE path LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{path}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_changes(limit: int = 50) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT timestamp,path,event,size_bytes FROM file_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def count_files() -> dict:
    with _connect() as c:
        total   = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        dirs    = c.execute("SELECT COUNT(*) FROM files WHERE type='dir'").fetchone()[0]
        files   = total - dirs
        history = c.execute("SELECT COUNT(*) FROM file_history").fetchone()[0]
    return {"total": total, "files": files, "dirs": dirs, "history_events": history}


# ── templates ──────────────────────────────────────────────────────────────────

def upsert_template(name: str, project_type: str, root_path: str,
                    key_files: list, conventions: dict = None):
    now = _ts()
    with _lock:
        with _connect() as c:
            exists = c.execute("SELECT id FROM templates WHERE root_path=?", (root_path,)).fetchone()
            kf     = json.dumps(key_files)
            cv     = json.dumps(conventions or {})
            if exists:
                c.execute(
                    "UPDATE templates SET name=?,project_type=?,key_files=?,conventions=?,updated_at=? WHERE root_path=?",
                    (name, project_type, kf, cv, now, root_path),
                )
            else:
                c.execute(
                    "INSERT INTO templates (name,project_type,root_path,key_files,conventions,detected_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (name, project_type, root_path, kf, cv, now, now),
                )


def get_templates(project_type: str = "") -> list[dict]:
    with _connect() as c:
        if project_type:
            rows = c.execute(
                "SELECT * FROM templates WHERE project_type=? ORDER BY updated_at DESC",
                (project_type,),
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM templates ORDER BY updated_at DESC").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["key_files"]   = json.loads(d["key_files"])
        d["conventions"] = json.loads(d["conventions"] or "{}")
        result.append(d)
    return result


# ── knowledge ─────────────────────────────────────────────────────────────────

def save_knowledge(category: str, title: str, body: str, source_path: str = ""):
    now = _ts()
    with _lock:
        with _connect() as c:
            existing = c.execute(
                "SELECT id FROM knowledge WHERE title=? AND category=?", (title, category)
            ).fetchone()
            if existing:
                c.execute(
                    "UPDATE knowledge SET body=?,source_path=?,updated_at=? WHERE id=?",
                    (body, source_path, now, existing["id"]),
                )
            else:
                c.execute(
                    "INSERT INTO knowledge (category,title,body,source_path,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (category, title, body, source_path, now, now),
                )


def get_knowledge(category: str = "", search: str = "") -> list[dict]:
    with _connect() as c:
        clauses, params = [], []
        if category:
            clauses.append("category = ?"); params.append(category)
        if search:
            clauses.append("(title LIKE ? OR body LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = c.execute(
            f"SELECT category,title,body,source_path,updated_at FROM knowledge {where} ORDER BY updated_at DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ── scans ──────────────────────────────────────────────────────────────────────

def start_scan() -> int:
    with _lock:
        with _connect() as c:
            cur = c.execute(
                "INSERT INTO scans (started_at,status) VALUES (?,?)", (_ts(), "running")
            )
            return cur.lastrowid


def finish_scan(scan_id: int, indexed: int, changed: int, deleted: int):
    with _lock:
        with _connect() as c:
            c.execute(
                "UPDATE scans SET finished_at=?,files_indexed=?,files_changed=?,files_deleted=?,status=? WHERE id=?",
                (_ts(), indexed, changed, deleted, "done", scan_id),
            )


def get_last_scan() -> dict | None:
    with _connect() as c:
        row = c.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


# ── todos ──────────────────────────────────────────────────────────────────────

def add_todo(text: str, priority: str = "normal",
             due_date: str = "", source: str = "manual") -> int:
    with _lock:
        with _connect() as c:
            cur = c.execute(
                "INSERT INTO todos (text,priority,status,due_date,created_at,source) VALUES (?,?,?,?,?,?)",
                (text, priority, "open", due_date, _ts(), source),
            )
            return cur.lastrowid


def complete_todo(todo_id: int):
    with _lock:
        with _connect() as c:
            c.execute("UPDATE todos SET status='done', done_at=? WHERE id=?", (_ts(), todo_id))


def cancel_todo(todo_id: int):
    with _lock:
        with _connect() as c:
            c.execute("UPDATE todos SET status='cancelled' WHERE id=?", (todo_id,))


def get_todos(status: str = "open") -> list[dict]:
    with _connect() as c:
        if status == "all":
            rows = c.execute("SELECT * FROM todos ORDER BY priority DESC, created_at DESC").fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM todos WHERE status=? ORDER BY priority DESC, created_at DESC",
                (status,),
            ).fetchall()
    return [dict(r) for r in rows]


# ── prompt history ─────────────────────────────────────────────────────────────

def log_prompt(prompt: str, response: str = "", session_id: str = ""):
    with _lock:
        with _connect() as c:
            c.execute(
                "INSERT INTO prompt_history (timestamp,prompt,response,session_id) VALUES (?,?,?,?)",
                (_ts(), prompt[:2000], response[:2000], session_id),
            )


def get_prompt_history(limit: int = 20, session_id: str = "") -> list[dict]:
    with _connect() as c:
        if session_id:
            rows = c.execute(
                "SELECT timestamp,prompt,response,session_id FROM prompt_history "
                "WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT timestamp,prompt,response,session_id FROM prompt_history "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]
