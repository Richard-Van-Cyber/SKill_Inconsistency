from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvidenceSpan:
    file: str
    line_start: Optional[int]
    line_end: Optional[int]
    span_text: str


@dataclass
class AgentImpact:
    blocks_execution: bool
    produces_silent_error: bool
    impact_description: str
    # How strong the claim is. Only "verified" means a failure was observed or
    # can be pointed at line-by-line; "may_block_if" covers conditional claims
    # such as "if this dependency is missing the import fails".
    # This field exists so downstream repair decisions can weight findings
    # instead of treating every high/medium as equally actionable.
    impact_class: str = "may_block_if"   # verified | may_block_if | silent | cosmetic


# Confidence levels, from strongest to weakest evidence:
#   verified    — a deterministic checker, or an exact line match
#   inferred    — the LLM read the code/doc and concluded it
#   speculative — conditional / hedged claim
CONFIDENCE_LEVELS = ("verified", "inferred", "speculative")


@dataclass
class Finding:
    id: str
    taxonomy_l1: str        # environmental | document | implementation
    taxonomy_l2: str
    taxonomy_l3: Optional[str]
    severity: str           # critical | high | medium | low
    agent_impact: AgentImpact
    evidence_a: EvidenceSpan
    evidence_b: Optional[EvidenceSpan]
    rationale: str
    validation_status: str  # confirmed | suppressed | hard_rule
    source_checker: str
    confidence: str = "inferred"        # verified | inferred | speculative
    # Filled in by the aggregator. Findings that describe the same underlying
    # defect share a root_cause_id, so the report can show both the raw count
    # and the number of distinct root causes.
    root_cause_id: Optional[str] = None
    contributing_checkers: list[str] = field(default_factory=list)

