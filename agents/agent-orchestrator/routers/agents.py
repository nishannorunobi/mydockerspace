import asyncio
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

import agent_registry as registry

router = APIRouter(prefix="/agents", tags=["agents"])

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFJA-Za-z]')
_strip = lambda s: _ANSI_RE.sub('', s)


@router.get("")
async def list_agents():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, registry.get_all_info)
    return {"agents": data}


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec:
        return JSONResponse({"error": "not found"}, status_code=404)
    loop = asyncio.get_event_loop()
    try:
        if spec.home and spec.start_script:
            def _launch():
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".log", mode="w")
                proc = subprocess.Popen(
                    ["bash", spec.start_script],
                    cwd=spec.home,
                    stdin=subprocess.DEVNULL,
                    stdout=tmp,
                    stderr=tmp,
                    start_new_session=True,
                    env=os.environ.copy(),
                )
                tmp.close()
                time.sleep(0.5)
                rc = proc.poll()
                if rc is not None:
                    out = Path(tmp.name).read_text(errors="replace")
                    return None, rc, _strip(out)
                return proc.pid, None, None
            pid, rc, out = await loop.run_in_executor(None, _launch)
            if rc is not None:
                return {"ok": False, "detail": f"Start script exited (code {rc})", "output": (out or "").strip()[:600]}
            return {"ok": True, "detail": f"Started (PID {pid})"}
        return {"ok": False, "detail": "start_script not configured for this agent"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec:
        return JSONResponse({"error": "not found"}, status_code=404)
    loop = asyncio.get_event_loop()
    try:
        if spec.home and spec.stop_script:
            await loop.run_in_executor(None, lambda: subprocess.run(
                ["bash", spec.stop_script],
                cwd=spec.home, capture_output=True, timeout=15,
            ))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/{agent_id}/logs/stream")
async def stream_logs(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)

    async def file_gen(log_path: Path):
        if log_path.exists():
            for line in log_path.read_text().splitlines()[-100:]:
                yield f"data: {json.dumps({'line': line + chr(10)})}\n\n"
        cursor = log_path.stat().st_size if log_path.exists() else 0
        while True:
            await asyncio.sleep(2)
            if log_path.exists():
                content = log_path.read_text()
                if len(content) > cursor:
                    for line in content[cursor:].splitlines():
                        yield f"data: {json.dumps({'line': line + chr(10)})}\n\n"
                    cursor = len(content)
            yield ": keepalive\n\n"

    async def empty_gen():
        yield f"data: {json.dumps({'line': 'No log source configured.\n'})}\n\n"
        while True:
            await asyncio.sleep(30)
            yield ": keepalive\n\n"

    if not spec:
        gen = empty_gen()
    elif spec.log_file:
        gen = file_gen(Path(spec.log_file))
    else:
        gen = empty_gen()

    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{agent_id}/memory")
async def list_memory(agent_id: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec or not spec.memory_dir:
        return {"files": []}
    mem = Path(spec.memory_dir)
    if not mem.exists():
        return {"files": []}
    return {"files": [f.name for f in sorted(mem.iterdir()) if f.is_file()]}


@router.get("/{agent_id}/memory/{filename}")
async def read_memory(agent_id: str, filename: str):
    spec = registry.SPEC_BY_ID.get(agent_id)
    if not spec or not spec.memory_dir:
        return {"error": "no memory dir"}
    path = Path(spec.memory_dir) / filename
    if not path.exists():
        return {"error": "not found"}
    return {"filename": filename, "content": path.read_text()}
