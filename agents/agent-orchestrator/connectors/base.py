from abc import ABC, abstractmethod


class AgentConnector(ABC):
    """
    Base class for all agent connectors.
    Each subclass knows how to dispatch a task to one type of agent.
    Configure which connector to use per-agent in agents.conf.
    """

    @abstractmethod
    async def dispatch(self, task: str) -> str:
        """Send task to the agent. Returns the agent's full response as a string."""

    def is_available(self) -> bool:
        """Quick reachability check. Override for remote agents."""
        return True
