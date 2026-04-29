"""
SQLite store for container events and periodic snapshots.
- container_events   : every state change (stopped, restarted, restart_failed, ...)
- container_snapshots: periodic status + stats records per container
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

_MEMORY = Path(__file__).resolve().parent / "memory"
DB_PATH  = _MEMORY / "events.db"
LOG_PATH = _MEMORY / "events.log"   # human-readable, shown in dashboard log viewer

_lock = threading.Lock()


def init():
    _MEMORY.mkdir(exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS container_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp      TEXT NOT NULL,
                container_id   TEXT NOT NULL,
                container_name TEXT NOT NULL,
                event_type     TEXT NOT NULL,
                details        TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS container_snapshots (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp      TEXT NOT NULL,
                container_id   TEXT NOT NULL,
                container_name TEXT NOT NULL,
                status         TEXT NOT NULL,
                image          TEXT,
                cpu_percent    TEXT,
                memory_usage   TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_name  ON container_events  (container_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_time  ON container_events  (timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snap_name    ON container_snapshots (container_name)")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def log_event(container_id: str, container_name: str, event_type: str, details: str = ""):
    ts = datetime.now().isoformat(timespec="seconds")
    with _lock:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO container_events "
                "(timestamp, container_id, container_name, event_type, details) "
                "VALUES (?,?,?,?,?)",
                (ts, container_id, container_name, event_type, details),
            )
        # Append to human-readable log
        try:
            with open(LOG_PATH, "a") as f:
                f.write(f"{ts} [{event_type.upper():18}] {container_name}: {details}\n")
        except OSError:
            pass


def log_snapshot(container_id: str, container_name: str, status: str,
                 image: str, cpu: str = "", memory: str = ""):
    with _lock:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO container_snapshots "
                "(timestamp, container_id, container_name, status, image, cpu_percent, memory_usage) "
                "VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"),
                 container_id, container_name, status, image, cpu, memory),
            )


def get_events(limit: int = 50, container_name: str = None) -> list[dict]:
    with _connect() as conn:
        if container_name:
            rows = conn.execute(
                "SELECT timestamp, container_id, container_name, event_type, details "
                "FROM container_events WHERE container_name=? ORDER BY id DESC LIMIT ?",
                (container_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT timestamp, container_id, container_name, event_type, details "
                "FROM container_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_snapshots(container_name: str = None, limit: int = 100) -> list[dict]:
    with _connect() as conn:
        if container_name:
            rows = conn.execute(
                "SELECT timestamp, container_id, container_name, status, image, cpu_percent, memory_usage "
                "FROM container_snapshots WHERE container_name=? ORDER BY id DESC LIMIT ?",
                (container_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT timestamp, container_id, container_name, status, image, cpu_percent, memory_usage "
                "FROM container_snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]
