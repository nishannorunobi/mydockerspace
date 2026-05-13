from abc import ABC, abstractmethod


class BaseLayer(ABC):
    supports_tools = False  # subclasses override

    def __init__(self, cfg: dict):
        self.name       = cfg["name"]
        self.model      = cfg["model"]
        self.max_tokens = cfg.get("max_tokens", 2048)
        self.judge      = cfg.get("judge")   # name of judge layer or "user"
        self.enabled    = cfg.get("enabled", True)

    def is_available(self) -> bool:
        return True

    @abstractmethod
    def text_complete(self, system: str, messages: list) -> str:
        """Simple text completion — no tools."""

    def messages_create(self, system: str, tools: list, messages: list):
        """Raw API call returning a response object with .content and .stop_reason.
        Only implemented by layers that support tools."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calls")
