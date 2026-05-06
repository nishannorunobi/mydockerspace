"""
Claude Code session viewer.
Streams what's being ingested into workspace agent memory
so the user can validate it in the dashboard.
"""
import asyncio
import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/claude-code", tags=["claude-code"])

WORKSPACE_DB = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "agents" / "workspace-agent" / "workspace" / "memory" / "workspace.db"
)

_SKIP = ("<task-notification>", "<system-reminder>", "<ide_selection>")


def _read_exchanges(limit: int = 60, after_id: int = 0) -> list[dict]:
    if not WORKSPACE_DB.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{WORKSPACE_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, timestamp, prompt, response, session_id "
            "FROM prompt_history WHERE id > ? ORDER BY id ASC LIMIT ?",
            (after_id, limit),
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            p = (r["prompt"] or "").strip()
            if any(p.startswith(s) for s in _SKIP):
                continue
            result.append(dict(r))
        return result
    except Exception:
        return []


@router.get("/history")
def get_history(limit: int = 60, after_id: int = 0):
    return {"exchanges": _read_exchanges(limit=limit, after_id=after_id)}


@router.get("/stream")
async def stream_exchanges():
    """SSE — sends recent history on connect, then polls for new rows every 4s."""
    async def gen():
        history = _read_exchanges(limit=40, after_id=0)
        last_id = 0
        for ex in history:
            yield f"data: {json.dumps(ex)}\n\n"
            last_id = max(last_id, ex["id"])

        while True:
            await asyncio.sleep(5)
            new_rows = _read_exchanges(limit=50, after_id=last_id)
            for ex in new_rows:
                yield f"data: {json.dumps(ex)}\n\n"
                last_id = max(last_id, ex["id"])
            yield ": keepalive\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
