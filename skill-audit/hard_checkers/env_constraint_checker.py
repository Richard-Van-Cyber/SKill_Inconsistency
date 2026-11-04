from __future__ import annotations

import re

from models.finding import AgentImpact, EvidenceSpan, Finding
from models.preflight import CodeFacts
from models.skill_map import Component, SkillMap

_FINDING_COUNTER = 0


def _next_id() -> str:
    global _FINDING_COUNTER
    _FINDING_COUNTER += 1
    return f"ENV-{_FINDING_COUNTER:03d}"


# (rule_name, doc_patterns, code_indicators, description)
_RULES: list[tuple[str, list[str], list[str], str]] = [
    (
        "platform_conflict",
        [r"跨平台", r"cross.?platform", r"platform.?independent", r"works on (all|any) (platform|os|system)"],
        ["winreg", "ctypes.windll", "ctypes.windll", "/proc/", "os.popen", "WINDOWS", "win32api"],
        "Skill claims cross-platform but code uses platform-specific APIs",
    ),
    (
        "network_conflict",
        [r"无需联网", r"offline", r"no.?network", r"no.?internet", r"standalone"],
        ["requests.get", "requests.post", "httpx.", "urllib.request", "http.client", "aiohttp"],
        "Skill claims offline/no-network but code makes HTTP calls",
    ),
    (
        "root_privilege_conflict",
        [r"无需.{0,4}root", r"no.{0,6}root", r"unprivileged", r"no.{0,6}(admin|sudo)"],
        ["os.setuid", "os.setgid", "subprocess.*sudo", "ctypes.*privilege"],
        "Skill claims no root required but code uses privileged operations",
    ),
    (
        "readonly_side_effect_conflict",
        [r"只读", r"read.?only", r"no.{0,6}(side.?effect|write|modif)", r"仅读取", r"不修改"],
        [],  # code signals come from CodeFacts flags, not text patterns
        "Skill claims read-only/no side effects but code performs writes or global mutations",
    ),
]



# Documentation trees that describe a library in general rather than the
# behaviour of this skill's own scripts. A generic "read-only" mention there is
# not a claim about the scripts, and treating it as one produced false
# "claims read-only but writes files" findings.
_NON_CLAIM_PATH_HINTS = (
    "references/", "reference/", "docs/", "doc/", "examples/", "example/",
    "tutorial", "guide", "changelog", "license",
)

_ARTIFACT_RE = None


def _is_reference_doc(path: str) -> bool:
    low = path.lower()
    return any(hint in low for hint in _NON_CLAIM_PATH_HINTS)


def _claim_mentions_code(claim_line: str, code_identifiers: set[str]) -> bool:
    """Does the sentence making the claim actually refer to this skill's code?

    "Reference.md says a Matrix is read-only" is not a claim that the skill
    writes nothing. The phrase must name the skill/script/tool, or name one of
    the skill's own functions or files as a whole word.
    """
    low = claim_line.lower()
    # Only phrases that clearly bind the claim to the skill's own artefact.
    # Bare "the script"/"the tool" matched ordinary prose such as a code
    # comment "# Read-only with pagination" and produced a false high finding.
    if any(word in low for word in ("this skill", "this tool", "this script",
                                    "does not write", "no side effect",
                                    "no file write", "doesn't write",
                                    "本技能", "该脚本", "本工具", "不写入", "无副作用")):
        return True
    # Whole-word match only: a substring test let a code sample's `readOnly`
    # property match the identifier `read` and pulled unrelated prose in scope.
    for ident in code_identifiers:
        if ident and re.search(rf"(?<![\w.-]){re.escape(ident.lower())}(?![\w.-])", low):
            return True
    return False


def _scope_check(desc_text: str, pattern: str, code_identifiers: set[str]) -> tuple[bool, str]:
    """Find the sentence that triggered the pattern and check its scope."""
    for line in desc_text.splitlines():
        if _search_doc(pattern, line):
            if _claim_mentions_code(line, code_identifiers):
                return True, line.strip()[:120]
            return False, line.strip()[:120]
    return False, ""


_CLI_FLAG_RE = re.compile(r"(?<!\w)--?[A-Za-z][\w.-]*(?:=[\w.-]+)?")


def _strip_cli_flags(text: str) -> str:
    """Remove CLI flags before pattern matching.

    ``qpdf --encrypt ... --modify=none`` matched the "no modify" claim pattern;
    a flag is an argument, not a statement about the skill's behaviour.
    """
    return _CLI_FLAG_RE.sub(" ", text)


def _search_doc(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, _strip_cli_flags(text), re.IGNORECASE))


def _search_code(indicator: str, text: str) -> bool:
    return indicator in text


def check(skill_map: SkillMap, code_facts: CodeFacts) -> list[Finding]:
    findings: list[Finding] = []

    # Aggregate all description component content, but ignore reference/tutorial
    # trees: they describe a library, not this skill's own behaviour.
    desc_components = [
        c for c in skill_map.components
        if c.component_type == "description" and not _is_reference_doc(c.source_file)
    ]
    desc_text = "\n".join(c.content for c in desc_components)

    # Aggregate all implementation component content
    impl_components = [c for c in skill_map.components if c.component_type == "implementation"]
    impl_text = "\n".join(c.content for c in impl_components)

    # Function names and source-file stems only. Imports were included before,
    # which pulled in module names that have nothing to do with the claim.
    code_identifiers = {f["name"] for f in getattr(code_facts, "functions", [])}
    for comp in skill_map.components:
        if comp.component_type == "implementation":
            stem = comp.source_file.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            code_identifiers.add(stem)

    for rule_name, doc_patterns, code_indicators, description in _RULES:
        # Check if any doc pattern matches
        matched_doc_pattern = next(
            (p for p in doc_patterns if _search_doc(p, desc_text)), None
        )
        if matched_doc_pattern is None:
            continue

        # The sentence that triggered the pattern must actually be about this
        # skill's code, otherwise it is prose in an unrelated document.
        in_scope, claim_line = _scope_check(desc_text, matched_doc_pattern, code_identifiers)
        confidence = "verified" if in_scope else "speculative"

        # Special case: readonly rule uses CodeFacts flags
        if rule_name == "readonly_side_effect_conflict":
            if not code_facts.has_file_write and not code_facts.has_global_mutation:
                continue
            code_evidence = "Code performs file writes or global state mutations (detected via AST analysis)"
        else:
            matched_code_indicator = next(
                (ind for ind in code_indicators if _search_code(ind, impl_text)), None
            )
            if matched_code_indicator is None:
                continue
            code_evidence = f"Code contains: '{matched_code_indicator}'"

        # Find which description component had the match
        matching_desc_comp: Component = desc_components[0]
        for comp in desc_components:
            if _search_doc(matched_doc_pattern, comp.content):
                matching_desc_comp = comp
                break

        findings.append(Finding(
            id=_next_id(),
            taxonomy_l1="environmental",
            taxonomy_l2="environment_fact_conflict",
            taxonomy_l3=None,
            severity="high" if in_scope else "low",
            agent_impact=AgentImpact(
                blocks_execution=in_scope,
                produces_silent_error=not in_scope,
                impact_description=(
                    description + ". Agent will fail in environments where the claimed constraint is enforced."
                    if in_scope else
                    "A read-only/offline/cross-platform phrase appears in a document, but the "
                    "sentence does not refer to this skill's own code. Likely prose, not a claim."
                ),
                impact_class="may_block_if" if in_scope else "cosmetic",
            ),
            confidence=confidence,
            evidence_a=EvidenceSpan(
                file=matching_desc_comp.source_file,
                line_start=matching_desc_comp.source_span[0] if matching_desc_comp.source_span else None,
                line_end=matching_desc_comp.source_span[1] if matching_desc_comp.source_span else None,
                span_text=(claim_line or f"Doc claims: (matched pattern '{matched_doc_pattern}')"),
            ),
            evidence_b=EvidenceSpan(
                file=impl_components[0].source_file if impl_components else "impl",
                line_start=None,
                line_end=None,
                span_text=code_evidence,
            ),
            rationale=f"Rule '{rule_name}': documentation asserts an environmental constraint that the implementation violates.",
            validation_status="hard_rule",
            source_checker="env_constraint_checker",
        ))

    return findings
