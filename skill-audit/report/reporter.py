from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import asdict

from models.finding import Finding
from models.skill_map import SkillMap


def _finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "taxonomy_l1": f.taxonomy_l1,
        "taxonomy_l2": f.taxonomy_l2,
        "taxonomy_l3": f.taxonomy_l3,
        "severity": f.severity,
        "agent_impact": {
            "blocks_execution": f.agent_impact.blocks_execution,
            "produces_silent_error": f.agent_impact.produces_silent_error,
            "impact_class": f.agent_impact.impact_class,
            "impact_description": f.agent_impact.impact_description,
        },
        "evidence": {
            "source_a": {
                "file": f.evidence_a.file,
                "line_start": f.evidence_a.line_start,
                "line_end": f.evidence_a.line_end,
                "span_text": f.evidence_a.span_text,
            },
            "source_b": {
                "file": f.evidence_b.file,
                "line_start": f.evidence_b.line_start,
                "line_end": f.evidence_b.line_end,
                "span_text": f.evidence_b.span_text,
            } if f.evidence_b else None,
        },
        "rationale": f.rationale,
        "validation_status": f.validation_status,
        "source_checker": f.source_checker,
        "confidence": f.confidence,
        "root_cause_id": f.root_cause_id,
        "contributing_checkers": f.contributing_checkers,
    }


def _build_summary(findings: list[Finding]) -> dict:
    total = len(findings)
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    suppressed = 0
    agent_blocking = 0

    for f in findings:
        if f.validation_status == "suppressed":
            suppressed += 1
        else:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        if f.agent_impact.blocks_execution:
            agent_blocking += 1

    return {
        "total_findings": total,
        "critical_count": counts["critical"],
        "high_count": counts["high"],
        "medium_count": counts["medium"],
        "low_count": counts["low"],
        "suppressed_count": suppressed,
        "agent_blocking_count": agent_blocking,
    }


def build_report(
    skill_dir: str,
    skill_map: SkillMap,
    findings: list[Finding],
    auditor_model: str,
    validator_model: str,
    taxonomy_version: str = "1.0",
) -> dict:
    skill_map_summary = {
        "total_files": len(skill_map.all_files),
        "files_read": len(skill_map.files_read),
        "sub_skills": skill_map.sub_skills,
        "sub_skill_relations": [
            {
                "from": r.from_skill,
                "to": r.to_skill,
                "type": r.relation_type,
                "description": r.description,
            }
            for r in skill_map.sub_skill_relations
        ],
        "components": [
            {
                "component_id": c.component_id,
                "component_type": c.component_type,
                "source_file": c.source_file,
                "source_span": list(c.source_span) if c.source_span else None,
            }
            for c in skill_map.components
        ],
        "comprehension_notes": skill_map.comprehension_notes,
    }

    return {
        "meta": {
            "skill_dir": skill_dir,
            "audit_time": datetime.now(timezone.utc).isoformat(),
            "auditor_model": auditor_model,
            "validator_model": validator_model,
            "taxonomy_version": taxonomy_version,
        },
        "skill_map_summary": skill_map_summary,
        "summary": _build_summary(findings),
        "findings": [_finding_to_dict(f) for f in findings],
    }
