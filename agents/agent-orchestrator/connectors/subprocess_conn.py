import asyncio
import subprocess
from pathlib import Path

from .base import AgentConnector


class SubprocessConnector(AgentConnector):
    """
    Runs an agent as a subprocess, passing the task as a positional CLI argument.
    Captures stdout + stderr as the result.

    agents.conf fields:
        connector     = subprocess
        connector_cmd = .venv/bin/python workspace/agent.py   # relative to home
        home          = /path/to/agent-dir                    # working directory
    """

    def __init__(self, cmd: str, cwd: str, timeout: int = 120):
        self._cmd     = cmd.split()
        self._cwd     = cwd
        self._timeout = timeout

    async def dispatch(self, task: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._run(task))

    def is_available(self) -> bool:
        return Path(self._cwd).exists()

    # ── internal ──────────────────────────────────────────────────────────────

    def _run(self, task: str) -> str:
        try:
            result = subprocess.run(
                self._cmd + [task],
                cwd=self._cwd,
                capture_output=True, text=True,
                timeout=self._timeout,
            )
            return (result.stdout + result.stderr).strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Agent timed out after {self._timeout}s"
        except Exception as e:
            return f"Subprocess connector error: {e}"
