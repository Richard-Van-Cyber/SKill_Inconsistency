from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Optional

from llm_client.base_client import BaseLLMClient
from models.finding import AgentImpact, EvidenceSpan, Finding
from models.preflight import PreflightData

SYSTEM_PROMPT = (
    "你是一位严谨的技术审计员。始终只输出合法的 JSON，不要在 JSON 之外添加任何说明。"
    "输出规则：rationale、impact_description 字段使用中文；span_text 字段保留原始文本不翻译。"
    "span_text 字段最多 150 个字符，超出截断。"
    "span_text 中的双引号必须用 \\\" 转义，换行符必须用 \\n 替代，不得直接换行。"
)

_CHECKER_COUNTER: dict[str, int] = {}


def _next_id(prefix: str) -> str:
    _CHECKER_COUNTER[prefix] = _CHECKER_COUNTER.get(prefix, 0) + 1
    return f"{prefix}-{_CHECKER_COUNTER[prefix]:03d}"


def _load_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "prompts", filename)
    with open(os.path.normpath(path), "r", encoding="utf-8") as f:
        return f.read()


def _extract_json(raw: str) -> dict:
    import re
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Attempt 1: standard parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: extract outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Attempt 3: strip control characters
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt 4: extract individual finding objects via regex and reconstruct
    # This handles cases where span_text contains unescaped quotes inside strings
    finding_pattern = re.compile(r'\{[^{}]*"taxonomy_l1"[^{}]*\}', re.DOTALL)
    matches = finding_pattern.findall(text)
    findings = []
    for m in matches:
        try:
            findings.append(json.loads(m))
        except json.JSONDecodeError:
            # Try to sanitize this individual object
            sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', m)
            try:
                findings.append(json.loads(sanitized))
            except json.JSONDecodeError:
                pass
    if findings:
        return {"findings": findings}

    # Give up — return empty
    return {"findings": []}


def _number_lines(text: str, start: int = 1) -> str:
    """Prefix each line with its number so findings can cite a real anchor.

    Without this the model could only answer `line_start: null`, and every
    finding then deduplicated on prose alone — one defect reported by four
    checkers stayed four findings.
    """
    return "\n".join(f"{start + i:>5d}| {line}" for i, line in enumerate(text.splitlines()))


def _format_skill_content(preflight: PreflightData) -> str:
    """Render all non-test components with line numbers for LLM prompts."""
    parts = []
    for comp in preflight.skill_map.components:
        if comp.component_type == "test":
            continue
        start = comp.source_span[0] if comp.source_span else 1
        header = f"=== [{comp.component_type.upper()}] {comp.source_file}"
        if comp.source_span:
            header += f" (lines {comp.source_span[0]}-{comp.source_span[1]})"
        header += " ==="
        parts.append(f"{header}\n{_number_lines(comp.content, start)}")
    return "\n\n".join(parts)


def _format_code_facts(preflight: PreflightData) -> str:
    cf = preflight.code_facts
    lines = [
        f"Entry function: {cf.entry_function}",
        f"Functions: {json.dumps([f['name'] for f in cf.functions])}",
        f"Raises: {json.dumps(cf.raises)}",
        f"HTTP URLs found in code: {json.dumps(cf.http_urls)}",
        f"Has file writes: {cf.has_file_write}",
        f"Has global mutations: {cf.has_global_mutation}",
        f"Imports: {json.dumps(cf.imports)}",
    ]
    # Include full function signatures
    for fn in cf.functions:
        sig = f"  def {fn['name']}({', '.join(p['name'] + (': ' + p['type'] if p['type'] else '') for p in fn['params'])}) -> {fn['return_type'] or 'unknown'}"
        lines.append(sig)
    return "\n".join(lines)


def _format_preflight_summary(preflight: PreflightData) -> str:
    if not preflight.hard_findings:
        return "None"
    lines = []
    for f in preflight.hard_findings:
        lines.append(f"- [{f.id}] {f.taxonomy_l2}/{f.taxonomy_l3}: {f.evidence_a.span_text[:120]}")
    return "\n".join(lines)


# The taxonomy is a closed vocabulary, but the model writes near-synonyms
# ("unimplemented_feature" for an over-promise, "dependency_version_drift" as a
# third name for the same D3 version clash). Mapping them onto one label is what
# makes cross-checker dedup possible.
_TAXONOMY_ALIASES: dict[tuple[str, str], str] = {
    ("implementation", "unimplemented_feature"): "over_promised",
    ("implementation", "overpromised"): "over_promised",
    ("implementation", "missing_parameter"): "over_promised",
    ("implementation", "missing_return_field"): "over_promised",
    ("implementation", "over_promised"): "over_promised",
    ("implementation", "under_promised"): "under_promised",
    ("implementation", "implicit_param_support"): "under_promised",
    ("implementation", "semantically_conflicting"): "semantic_conflict",
    ("implementation", "semantic_conflict"): "semantic_conflict",
    ("document", "interface_contract_mismatch"): "interface_contract_mismatch",
    ("document", "shared_concept_definition_conflict"): "shared_concept_definition_conflict",
    ("document", "cross_document_process_conflict"): "cross_document_process_conflict",
    ("environmental", "dependency_version_drift"): "dependency_version_drift",
    ("environmental", "external_resource_invalid"): "external_resource_invalid",
    ("environmental", "environment_fact_conflict"): "environment_fact_conflict",
    ("environmental", "external_service_contract_change"): "external_service_contract_change",
}


def _canonical_l2(l1: str, l2: str) -> str:
    l1 = (l1 or "").strip().lower()
    l2 = (l2 or "").strip().lower()
    if not l2 or l2 == "unknown":
        return l2 or "unknown"
    return _TAXONOMY_ALIASES.get((l1, l2), l2)


def _as_int(value) -> Optional[int]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_findings(data: dict, checker_name: str, id_prefix: str) -> list[Finding]:
    findings = []
    for raw in data.get("findings", []):
        ea = raw.get("evidence_a") or {}
        eb = raw.get("evidence_b")
        ai = raw.get("agent_impact") or {}
        l1 = raw.get("taxonomy_l1", "implementation")
        confidence = str(raw.get("confidence", "inferred")).strip().lower()
        if confidence not in ("verified", "inferred", "speculative"):
            confidence = "inferred"
        impact_class = str(ai.get("impact_class", "")).strip().lower()
        if impact_class not in ("verified", "may_block_if", "silent", "cosmetic"):
            impact_class = ("silent" if ai.get("produces_silent_error")
                            else "may_block_if" if ai.get("blocks_execution") else "cosmetic")
        # A finding can only claim to block execution if it says it is verified.
        blocks = bool(ai.get("blocks_execution", False)) and confidence == "verified"
        findings.append(Finding(
            id=_next_id(id_prefix),
            taxonomy_l1=l1,
            taxonomy_l2=_canonical_l2(l1, raw.get("taxonomy_l2", "unknown")),
            taxonomy_l3=raw.get("taxonomy_l3"),
            severity=raw.get("severity", "medium"),
            agent_impact=AgentImpact(
                blocks_execution=blocks,
                produces_silent_error=ai.get("produces_silent_error", False),
                impact_description=ai.get("impact_description", ""),
                impact_class=impact_class,
            ),
            evidence_a=EvidenceSpan(
                file=ea.get("file", "unknown"),
                line_start=_as_int(ea.get("line_start")),
                line_end=_as_int(ea.get("line_end")),
                span_text=ea.get("span_text", ""),
            ),
            evidence_b=EvidenceSpan(
                file=eb["file"],
                line_start=_as_int(eb.get("line_start")),
                line_end=_as_int(eb.get("line_end")),
                span_text=eb.get("span_text", ""),
            ) if eb else None,
            rationale=raw.get("rationale", ""),
            validation_status="confirmed",
            source_checker=checker_name,
            confidence=confidence,
        ))
    return findings


class BaseChecker(ABC):
    def __init__(self, client: BaseLLMClient, id_prefix: str):
        self.client = client
        self.id_prefix = id_prefix

    @abstractmethod
    def build_prompt(self, preflight: PreflightData) -> str: ...

    @property
    @abstractmethod
    def checker_name(self) -> str: ...

    async def run(self, preflight: PreflightData) -> list[Finding]:
        prompt = self.build_prompt(preflight)
        raw = await self.client.complete(prompt, system=SYSTEM_PROMPT, temperature=0.1)
        data = _extract_json(raw)
        return _parse_findings(data, self.checker_name, self.id_prefix)
