import asyncio
import importlib

from .base import AgentConnector


class DirectConnector(AgentConnector):
    """
    Calls a Python agent module directly in-process via its run_agent(task, history) function.
    The module must be importable (i.e. its parent directory must already be on sys.path).

    agents.conf fields:
        connector        = direct
        connector_module = workspace.agent   # dotted Python module path
    """

    def __init__(self, module_path: str):
        mod = importlib.import_module(module_path)
        self._run_agent = getattr(mod, "run_agent")

    async def dispatch(self, task: str) -> str:
        loop = asyncio.get_event_loop()
        history = await loop.run_in_executor(
            None, lambda: self._run_agent(task, [])
        )
        return self._extract(history)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract(history: list) -> str:
        """Pull the last assistant text out of a run_agent history list."""
        for msg in reversed(history):
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                texts = [
                    b["text"] for b in content
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
                ]
                if texts:
                    return " ".join(texts).strip()
        return "(no response from agent)"
