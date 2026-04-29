import asyncio
import json
import urllib.error
import urllib.request

from .base import AgentConnector


class HttpConnector(AgentConnector):
    """
    Calls an agent that exposes an HTTP API.
    Expects: POST {api_url}/api/tasks  →  {"result": "..."}

    agents.conf fields:
        connector = http
        api_url   = http://localhost:8002   # base URL of the agent server
    """

    def __init__(self, api_url: str, task_path: str = "/api/tasks"):
        base = api_url.rstrip("/")
        self._task_url   = base + task_path
        self._health_url = base + "/health"

    async def dispatch(self, task: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._post(task))

    def is_available(self) -> bool:
        try:
            urllib.request.urlopen(self._health_url, timeout=3)
            return True
        except Exception:
            return False

    # ── internal ──────────────────────────────────────────────────────────────

    def _post(self, task: str) -> str:
        payload = json.dumps({"task": task}).encode()
        req = urllib.request.Request(
            self._task_url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read())
                return body.get("result", str(body))
        except urllib.error.HTTPError as e:
            return f"HTTP {e.code}: {e.read().decode()}"
        except Exception as e:
            return f"HTTP connector error: {e}"
