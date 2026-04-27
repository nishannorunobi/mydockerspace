import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional


class WorkspaceMonitor(threading.Thread):
    INTERVAL = 15  # seconds between polls
    SUPPRESS  = ("workspace-agent/memory/",)  # suppress internal agent writes

    def __init__(
        self,
        workspace_root: Path,
        memory_dir: Path,
        on_change: Optional[Callable] = None,
    ):
        super().__init__(daemon=True)
        self._root       = workspace_root
        self._memory     = memory_dir
        self._on_change  = on_change
        self._stop       = threading.Event()
        self._last: Optional[str] = None

    def stop(self):
        self._stop.set()

    def run(self):
        self._last = self._status()
        while not self._stop.wait(self.INTERVAL):
            self._check()

    # ── internals ──────────────────────────────────────────────────────────────

    def _status(self) -> str:
        try:
            r = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(self._root),
                capture_output=True, text=True, timeout=10,
            )
            return r.stdout.strip()
        except Exception:
            return ""

    def _visible(self, line: str) -> bool:
        path = line[3:].strip() if len(line) > 3 else ""
        return not any(path.startswith(s) for s in self.SUPPRESS)

    def _check(self):
        current = self._status()
        if current == self._last:
            return

        old = set(self._last.splitlines()) if self._last else set()
        new = set(current.splitlines())

        added   = sorted(l for l in new - old if self._visible(l))
        removed = sorted(l for l in old - new if self._visible(l))

        self._last = current

        if not added and not removed:
            return

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save(ts, added, removed)
        if self._on_change:
            self._on_change(ts, added, removed)

    def _save(self, ts: str, added: list, removed: list):
        try:
            self._memory.mkdir(exist_ok=True)
            lines = [f"**{ts}** — auto-detected"]
            for l in added:
                lines.append(f"  + {l}")
            for l in removed:
                lines.append(f"  - {l}")
            entry = "\n".join(lines)
            path  = self._memory / "change_log.md"
            existing = path.read_text() if path.exists() else "# Change Log\n"
            path.write_text(existing + f"\n\n---\n{entry}")
        except Exception:
            pass
