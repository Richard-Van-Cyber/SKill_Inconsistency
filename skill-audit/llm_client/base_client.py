from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str = "", temperature: float = 0.1, max_tokens: int = 4096) -> str:
        """Send a prompt and return the response text."""
        ...

    @abstractmethod
    def usage_summary(self) -> dict:
        """Return cumulative token usage stats."""
        ...
