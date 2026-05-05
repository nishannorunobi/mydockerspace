import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import agent_registry as registry
import alert_engine   as alert_eng

router = APIRouter(prefix="/events", tags=["events"])
log    = logging.getLogger(__name__)


# ── Cross-agent event bus ──────────────────────────────────────────────────────

class AgentEventBody(BaseModel):
    source:    str        # agent that fired this event
    event:     str        # event type
    container: str = ""  # container name (if from inside a container)
    data:      dict = {} # event-specific payload


@router.post("/notify")
def notify_event(body: AgentEventBody):
    """
    Host-side cross-agent event bus. Any agent running on the host can POST here
    to inform the orchestrator about something that happened.

    The orchestrator logs the event and broadcasts it to the SSE stream so the
    dashboard and other subscribers know about it in real time.
    """
    event_payload = {
        "type":      "agent_event",
        "source":    body.source,
        "event":     body.event,
        "container": body.container,
        "data":      body.data,
        "ts":        datetime.now().isoformat(),
    }
    log.info("agent_event from=%s event=%s data=%s", body.source, body.event, body.data)
    alert_eng.broadcast(event_payload)
    return {"ok": True, "event": body.event, "source": body.source}


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
