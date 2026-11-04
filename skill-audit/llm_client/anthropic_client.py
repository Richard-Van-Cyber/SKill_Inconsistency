from __future__ import annotations

import anthropic
from llm_client.base_client import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str, temperature: float = 0.1, max_tokens: int = 4096, base_url: str | None = None):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.AsyncAnthropic(**kwargs)
        self.model = model
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens

        # Cumulative usage counters
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    async def complete(self, prompt: str, system: str = "", temperature: float | None = None, max_tokens: int | None = None) -> str:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.default_max_tokens,
            temperature=temperature if temperature is not None else self.default_temperature,
            system=system or "You are a precise code and documentation auditor.",
            messages=[{"role": "user", "content": prompt}],
        )
        # Track usage
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens
        self.total_calls += 1
        return response.content[0].text

    def usage_summary(self) -> dict:
        return {
            "calls": self.total_calls,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
        }
