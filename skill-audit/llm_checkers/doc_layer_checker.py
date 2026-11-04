from __future__ import annotations

import json

from llm_checkers.base_checker import (
    BaseChecker, _format_skill_content,
    _format_preflight_summary, _load_prompt
)
from models.preflight import PreflightData


class DocLayerChecker(BaseChecker):
    checker_name = "doc_layer_checker"

    def __init__(self, client):
        super().__init__(client, "DOC-LLM")
        self._template = _load_prompt("doc_layer.md")

    def build_prompt(self, preflight: PreflightData) -> str:
        relations = [
            {
                "from": r.from_skill,
                "to": r.to_skill,
                "type": r.relation_type,
                "description": r.description,
            }
            for r in preflight.skill_map.sub_skill_relations
        ]
        return (
            self._template
            .replace("{skill_content}", _format_skill_content(preflight))
            .replace("{sub_skill_relations}", json.dumps(relations, ensure_ascii=False, indent=2))
            .replace("{preflight_summary}", _format_preflight_summary(preflight))
        )
