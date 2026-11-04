from __future__ import annotations

from llm_checkers.base_checker import (
    BaseChecker, _format_skill_content, _format_code_facts,
    _format_preflight_summary, _load_prompt
)
from models.preflight import PreflightData


class EnvLayerChecker(BaseChecker):
    checker_name = "env_layer_checker"

    def __init__(self, client):
        super().__init__(client, "ENV-LLM")
        self._template = _load_prompt("env_layer.md")

    def build_prompt(self, preflight: PreflightData) -> str:
        return (
            self._template
            .replace("{skill_content}", _format_skill_content(preflight))
            .replace("{preflight_summary}", _format_preflight_summary(preflight))
        )
