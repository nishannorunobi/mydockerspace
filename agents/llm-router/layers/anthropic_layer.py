import os
import anthropic as _sdk

from .base import BaseLayer


class AnthropicLayer(BaseLayer):
    supports_tools = True

    def __init__(self, cfg: dict, api_key: str = ""):
        super().__init__(cfg)
        self._client = _sdk.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""))

    def is_available(self) -> bool:
        return bool(self._client.api_key)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _sys_block(self, system: str) -> list:
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    def _cached_tools(self, tools: list) -> list:
        if not tools:
            return tools
        return tools[:-1] + [{**tools[-1], "cache_control": {"type": "ephemeral"}}]

    # ── public API ─────────────────────────────────────────────────────────────

    def text_complete(self, system: str, messages: list) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._sys_block(system),
            messages=messages,
        )
        return " ".join(b.text for b in resp.content if b.type == "text").strip()

    def messages_create(self, system: str, tools: list, messages: list):
        """Return raw Anthropic response object (content blocks + stop_reason)."""
        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._sys_block(system),
            messages=messages,
        )
        if tools:
            kwargs["tools"] = self._cached_tools(tools)
        return self._client.messages.create(**kwargs)
