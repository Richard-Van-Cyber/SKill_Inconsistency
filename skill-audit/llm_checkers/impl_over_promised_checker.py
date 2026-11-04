from __future__ import annotations

from llm_checkers.base_checker import (
    BaseChecker, _format_skill_content, _format_code_facts,
    _format_preflight_summary, _load_prompt
)
from models.preflight import PreflightData


class ImplOverPromisedChecker(BaseChecker):
    checker_name = "impl_over_promised_checker"

    def __init__(self, client):
        super().__init__(client, "OVER")
        self._template = _load_prompt("impl_over_promised.md")

    def build_prompt(self, preflight: PreflightData) -> str:
        return (
            self._template
            .replace("{skill_content}", _format_skill_content(preflight))
            .replace("{code_facts}", _format_code_facts(preflight))
            .replace("{schema_diff}", preflight.schema_diff_summary or "None")
            .replace("{preflight_summary}", _format_preflight_summary(preflight))
        )
