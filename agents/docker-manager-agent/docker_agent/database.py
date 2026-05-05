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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_registrations (
                id                TEXT PRIMARY KEY,
                name              TEXT NOT NULL,
                container         TEXT NOT NULL,
                port              INTEGER NOT NULL,
                agent_path        TEXT NOT NULL,
                network           TEXT NOT NULL DEFAULT 'ums-network',
                compose_dir       TEXT,
                clean_restart_cmd TEXT,
                registered_at     TEXT NOT NULL
            )
        """)
        # Migrate existing tables that were created before these columns existed
        for col, default in [("compose_dir", "NULL"), ("clean_restart_cmd", "NULL")]:
            try:
                conn.execute(f"ALTER TABLE agent_registrations ADD COLUMN {col} TEXT DEFAULT {default}")
            except Exception:
                pass  # column already exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_comms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                agent_id    TEXT NOT NULL,
                direction   TEXT NOT NULL,
                path        TEXT,
                payload     TEXT,
                result      TEXT,
                duration_ms INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_name  ON container_events  (container_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_time  ON container_events  (timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snap_name    ON container_snapshots (container_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comms_agent  ON agent_comms (agent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comms_time   ON agent_comms (timestamp)")


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


# ── Agent registry ─────────────────────────────────────────────────────────────

def register_agent(id: str, name: str, container: str, port: int,
                   agent_path: str, network: str = "ums-network",
                   compose_dir: str = "", clean_restart_cmd: str = ""):
    ts = datetime.now().isoformat(timespec="seconds")
    with _lock:
        with _connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO agent_registrations
                (id, name, container, port, agent_path, network, compose_dir, clean_restart_cmd, registered_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (id, name, container, port, agent_path, network, compose_dir, clean_restart_cmd, ts))


def get_agent_registrations() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_registrations ORDER BY registered_at"
        ).fetchall()
    return [dict(r) for r in rows]


def get_agent_registration(agent_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agent_registrations WHERE id=?", (agent_id,)
        ).fetchone()
    return dict(row) if row else None


def unregister_agent(agent_id: str):
    with _lock:
        with _connect() as conn:
            conn.execute("DELETE FROM agent_registrations WHERE id=?", (agent_id,))


def get_registration_by_container(container_name: str) -> dict | None:
    """Return the first agent registration whose container matches container_name."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agent_registrations WHERE container=? LIMIT 1", (container_name,)
        ).fetchone()
    return dict(row) if row else None


def seed_default_agents():
    """Register built-in container agents. Always refreshes compose_dir / clean_restart_cmd."""
    _WORKSPACE = "/home/nishan/myworkspace"
    defaults = [
        dict(id="db-agent",  name="DB Agent",
             container="mypostgresql_db-container", port=8890,
             agent_path="/mypostgresql_db/db-agent/start.sh", network="ums-network",
             compose_dir=f"{_WORKSPACE}/projectspace/mypostgresql_db/dockerspace/host_scripts",
             clean_restart_cmd="FORCE_RECREATE_CONTAINER=true bash start.sh"),
        dict(id="ums-agent", name="UMS Agent",
             container="ums-app", port=8891,
             agent_path="/ums/ums-agent/start.sh", network="ums-network",
             compose_dir=f"{_WORKSPACE}/projectspace/ums/dockerspace/host_scripts",
             clean_restart_cmd="make restart"),
    ]
    for d in defaults:
        existing = get_agent_registration(d["id"])
        if not existing:
            register_agent(**d)
        else:
            # Always refresh compose fields so they stay current
            with _lock:
                with _connect() as conn:
                    conn.execute(
                        "UPDATE agent_registrations SET compose_dir=?, clean_restart_cmd=? WHERE id=?",
                        (d["compose_dir"], d["clean_restart_cmd"], d["id"]),
                    )


# ── Agent communication log ────────────────────────────────────────────────────

def log_agent_comm(agent_id: str, direction: str, path: str = "",
                   payload: str = "", result: str = "", duration_ms: int = 0):
    ts = datetime.now().isoformat(timespec="seconds")
    with _lock:
        with _connect() as conn:
            conn.execute("""
                INSERT INTO agent_comms
                (timestamp, agent_id, direction, path, payload, result, duration_ms)
                VALUES (?,?,?,?,?,?,?)
            """, (ts, agent_id, direction, path,
                  (payload or "")[:1000], (result or "")[:2000], duration_ms))


def get_agent_comms(agent_id: str = None, limit: int = 50) -> list[dict]:
    with _connect() as conn:
        if agent_id:
            rows = conn.execute(
                "SELECT * FROM agent_comms WHERE agent_id=? ORDER BY id DESC LIMIT ?",
                (agent_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_comms ORDER BY id DESC LIMIT ?", (limit,)
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
