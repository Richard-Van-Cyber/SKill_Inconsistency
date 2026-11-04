from __future__ import annotations

import re
from models.finding import Finding

# Severity order used for sorting and for keeping the strongest claim when
# several findings collapse into one root cause.
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "be", "with", "by", "as", "at", "it", "this", "that", "from", "not",
    "de", "la", "el", "en", "y", "o", "un", "una",
}


def _canon_tokens(text: str) -> frozenset[str]:
    """Normalise a span of evidence into comparable tokens.

    The previous key used the raw first 80 characters of an LLM-written quote,
    so the same defect reported twice with slightly different wording was never
    merged. Comparing token sets instead of exact strings fixes that.
    """
    text = text.lower()
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[`*_>#|\[\](){}:,;\"'\u201c\u201d\u2018\u2019]", " ", text)
    tokens = [t for t in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff_.\-/]+", text) if t]
    return frozenset(t for t in tokens if len(t) > 1 and t not in _STOPWORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def _evidence_tokens(f: Finding) -> frozenset[str]:
    parts = [f.evidence_a.span_text]
    if f.evidence_b:
        parts.append(f.evidence_b.span_text)
    parts.append(f.rationale)
    return _canon_tokens(" ".join(parts))


def _same_root(a: Finding, b: Finding, threshold: float = 0.4) -> bool:
    """Two findings share a root cause when taxonomy, location and evidence agree."""
    if a.taxonomy_l2 != b.taxonomy_l2:
        return False
    same_file = a.evidence_a.file == b.evidence_a.file
    same_line = (
        a.evidence_a.line_start is not None
        and a.evidence_a.line_start == b.evidence_a.line_start
    )
    if same_file and same_line:
        return True
    score = _jaccard(_evidence_tokens(a), _evidence_tokens(b))
    return score >= (threshold if same_file else 0.6)


def _merge(group: list[Finding]) -> Finding:
    """Collapse a root-cause group into its strongest representative."""
    group = sorted(
        group,
        key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), 0 if f.confidence == "verified" else 1),
    )
    keep = group[0]
    checkers: list[str] = []
    for f in group:
        for name in [f.source_checker, *f.contributing_checkers]:
            if name and name not in checkers:
                checkers.append(name)
    keep.contributing_checkers = [c for c in checkers if c != keep.source_checker]
    for f in group:
        if keep.evidence_a.line_start is None and f.evidence_a.line_start is not None:
            keep.evidence_a = f.evidence_a
        if keep.evidence_b is None and f.evidence_b is not None:
            keep.evidence_b = f.evidence_b
    if keep.confidence == "speculative" and any(f.confidence == "verified" for f in group):
        keep.confidence = "verified"
    # An execution-blocking claim survives only if a verified member made it.
    if keep.agent_impact.blocks_execution and not any(
        f.agent_impact.blocks_execution and f.confidence == "verified" for f in group
    ):
        keep.agent_impact.blocks_execution = False
        if keep.agent_impact.impact_class == "verified":
            keep.agent_impact.impact_class = "may_block_if"
    return keep


def aggregate(
    hard_findings: list[Finding],
    llm_findings: list[Finding],
    include_suppressed: bool = False,
) -> list[Finding]:
    """Merge hard-rule and LLM findings, collapse root causes, assign final IDs.

    Stage 1: exact-key dedup (taxonomy + file + line + normalised span).
    Stage 2: semantic root-cause clustering (taxonomy + location + evidence
             token overlap), which catches one defect reported by several
             checkers.

    ``root_cause_id`` records the cluster and ``contributing_checkers`` records
    which checkers independently found the same thing.
    """
    all_findings = hard_findings + llm_findings

    if not include_suppressed:
        all_findings = [f for f in all_findings if f.validation_status != "suppressed"]

    seen: set[tuple] = set()
    unique: list[Finding] = []
    for f in all_findings:
        key = (
            f.taxonomy_l2,
            f.taxonomy_l3 or "",
            f.evidence_a.file,
            f.evidence_a.line_start,
            " ".join(sorted(_canon_tokens(f.evidence_a.span_text)))[:160],
        )
        if key not in seen:
            seen.add(key)
            unique.append(f)

    unique.sort(key=lambda f: (
        _SEVERITY_ORDER.get(f.severity, 99),
        f.taxonomy_l2,
        f.taxonomy_l3 or "",
        f.evidence_a.file,
        f.evidence_a.line_start or 0,
        f.source_checker,
    ))
    clusters: list[list[Finding]] = []
    for f in unique:
        for cluster in clusters:
            if _same_root(cluster[0], f):
                cluster.append(f)
                break
        else:
            clusters.append([f])

    merged = [_merge(c) for c in clusters]
    merged.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.evidence_a.file))
    for i, f in enumerate(merged, start=1):
        f.id = f"F-{i:03d}"
        f.root_cause_id = f"RC-{i:03d}"
    return merged


def root_cause_stats(findings: list[Finding]) -> dict:
    """Counts for the report: findings vs distinct root causes."""
    by_severity: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_confidence[f.confidence] = by_confidence.get(f.confidence, 0) + 1
    return {
        "root_causes": len(findings),
        "by_severity": by_severity,
        "by_confidence": by_confidence,
    }
