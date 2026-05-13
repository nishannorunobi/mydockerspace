import json
try:
    import requests as _requests
except ImportError:
    _requests = None

from .base import BaseLayer


class OllamaLayer(BaseLayer):
    supports_tools = False  # text-only; no Anthropic-format tool_use

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.base_url = cfg.get("base_url", "http://localhost:11434").rstrip("/")

    def is_available(self) -> bool:
        if _requests is None:
            return False
        try:
            r = _requests.get(f"{self.base_url}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def text_complete(self, system: str, messages: list) -> str:
        if _requests is None:
            raise RuntimeError("requests library not installed")

        payload_msgs = []
        if system:
            payload_msgs.append({"role": "system", "content": system})

        for m in messages:
            role    = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                # flatten content blocks to plain text
                content = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            if role in ("user", "assistant") and content:
                payload_msgs.append({"role": role, "content": content})

        resp = _requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model":  self.model,
                "messages": payload_msgs,
                "stream": False,
                "options": {"num_predict": self.max_tokens},
            },
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
