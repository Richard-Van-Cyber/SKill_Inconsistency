"""Second-pass review of LLM findings.

Two changes over the first implementation:
  * findings are validated in a single batched call instead of one call each
    (the previous version spent 172 of 241 total calls here and suppressed
    nothing);
  * rule-based suppression is applied here but counted separately, so the
    report can distinguish "filtered by rule" from "the reviewer rejected it".
"""
from __future__ import annotations

import json

from llm_client.base_client import BaseLLMClient
from llm_checkers.base_checker import _extract_json, _load_prompt, _format_skill_content
from models.finding import Finding
from models.preflight import PreflightData

SYSTEM_PROMPT = (
    "你是一位严谨的技术审计员。始终只输出合法的 JSON，不要在 JSON 之外添加任何说明。"
    "reason 字段使用中文。JSON 字符串中不得包含未转义的引号或换行符。"
)

BATCH_SIZE = 12


def _finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "taxonomy_l1": f.taxonomy_l1,
        "taxonomy_l2": f.taxonomy_l2,
        "taxonomy_l3": f.taxonomy_l3,
        "severity": f.severity,
        "confidence": f.confidence,
        "agent_impact": {
            "blocks_execution": f.agent_impact.blocks_execution,
            "produces_silent_error": f.agent_impact.produces_silent_error,
            "impact_class": f.agent_impact.impact_class,
            "impact_description": f.agent_impact.impact_description,
        },
        "evidence_a": {"file": f.evidence_a.file, "span_text": f.evidence_a.span_text},
        "evidence_b": {"file": f.evidence_b.file, "span_text": f.evidence_b.span_text} if f.evidence_b else None,
        "rationale": f.rationale,
        "source_checker": f.source_checker,
    }


def _apply_verdicts(findings: list[Finding], verdicts: dict) -> None:
    for finding in findings:
        verdict = verdicts.get(finding.id)
        if not isinstance(verdict, dict):
            # Absent from the batch reply: keep it, do not silently drop it.
            finding.validation_status = "confirmed"
            continue
        status = str(verdict.get("verdict", "confirmed")).lower()
        if status not in ("confirmed", "suppressed"):
            status = "confirmed"
        finding.validation_status = status
        adjusted = verdict.get("adjusted_severity")
        if adjusted in ("critical", "high", "medium", "low"):
            finding.severity = adjusted
        new_conf = str(verdict.get("confidence", "")).lower()
        if new_conf in ("verified", "inferred", "speculative"):
            finding.confidence = new_conf
        if finding.validation_status == "suppressed":
            # A suppressed finding must not keep claiming it blocks execution.
            finding.agent_impact.blocks_execution = False


def split_by_rule(findings: list[Finding], report_under_promised: bool) -> tuple[list[Finding], list[Finding]]:
    """Rule-based partitioning: returns (needs_review, rule_suppressed)."""
    needs_review, suppressed = [], []
    for f in findings:
        if f.taxonomy_l2 == "under_promised" and not report_under_promised:
            f.validation_status = "suppressed"
            suppressed.append(f)
        else:
            needs_review.append(f)
    return needs_review, suppressed


async def validate(
    findings: list[Finding],
    preflight: PreflightData,
    client: BaseLLMClient,
    report_under_promised: bool = False,
) -> list[Finding]:
    """Re-evaluate LLM findings; hard-rule findings pass through untouched."""
    template = _load_prompt("criticality_validation.md")
    skill_content_excerpt = _format_skill_content(preflight)[:6000]

    results: list[Finding] = []
    to_review: list[Finding] = []
    for finding in findings:
        if finding.validation_status == "hard_rule":
            results.append(finding)
        else:
            to_review.append(finding)

    to_review, rule_suppressed = split_by_rule(to_review, report_under_promised)
    results.extend(rule_suppressed)

    for start in range(0, len(to_review), BATCH_SIZE):
        batch = to_review[start:start + BATCH_SIZE]
        payload = json.dumps([_finding_to_dict(f) for f in batch], ensure_ascii=False, indent=2)
        prompt = (
            template
            .replace("{finding_json}", payload)
            .replace("{skill_content}", skill_content_excerpt)
        )
        try:
            raw = await client.complete(prompt, system=SYSTEM_PROMPT, temperature=0.0)
            data = _extract_json(raw)
            verdicts = {}
            for item in data.get("verdicts", data.get("findings", [])) or []:
                if isinstance(item, dict) and item.get("id"):
                    verdicts[item["id"]] = item
            _apply_verdicts(batch, verdicts)
        except Exception:
            # Conservative default: keep every finding in the batch.
            _apply_verdicts(batch, {})
        results.extend(batch)

    return results
