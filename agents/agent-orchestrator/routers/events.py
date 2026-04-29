import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import agent_registry as registry
import alert_engine   as alert_eng

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def events_stream():
    q = alert_eng.subscribe()

    async def generate():
        try:
            data = await asyncio.get_event_loop().run_in_executor(None, registry.get_all_info)
            yield f"data: {json.dumps({'type': 'init', 'agents': data})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            alert_eng.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
