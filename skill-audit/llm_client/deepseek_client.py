from __future__ import annotations

import openai
from llm_client.base_client import BaseLLMClient


class DeepSeekClient(BaseLLMClient):
    """OpenAI-compatible client for DeepSeek models."""

    def __init__(self, api_key: str, model: str, temperature: float = 0.1, max_tokens: int = 4096, base_url: str = "https://api.deepseek.com"):
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=300.0,  # 5 minutes — this relay API is slow on long prompts
        )
        self.model = model
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens

        # Cumulative usage counters
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    async def complete(self, prompt: str, system: str = "", temperature: float | None = None, max_tokens: int | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        else:
            messages.append({"role": "system", "content": "You are a precise code and documentation auditor."})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature if temperature is not None else self.default_temperature,
            max_tokens=max_tokens or self.default_max_tokens,
        )

        usage = response.usage
        if usage:
            self.total_input_tokens += usage.prompt_tokens
            self.total_output_tokens += usage.completion_tokens
        self.total_calls += 1

        return response.choices[0].message.content or ""

    def usage_summary(self) -> dict:
        return {
            "calls": self.total_calls,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
        }
