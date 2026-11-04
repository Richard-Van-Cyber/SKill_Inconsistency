from __future__ import annotations

from core.config import LLMConfig
from llm_client.base_client import BaseLLMClient
from llm_client.anthropic_client import AnthropicClient
from llm_client.deepseek_client import DeepSeekClient


def build_llm_client(cfg: LLMConfig) -> BaseLLMClient:
    if cfg.provider == "anthropic":
        return AnthropicClient(
            api_key=cfg.api_key,
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            base_url=cfg.base_url,
        )
    if cfg.provider == "deepseek":
        return DeepSeekClient(
            api_key=cfg.api_key,
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            base_url=cfg.base_url or "https://api.deepseek.com",
        )
    raise ValueError(f"Unsupported LLM provider: '{cfg.provider}'. Supported: anthropic, deepseek")
