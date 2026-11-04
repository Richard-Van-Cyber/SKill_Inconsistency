from __future__ import annotations

import json
import re
from typing import Any, Optional

from models.finding import AgentImpact, EvidenceSpan, Finding
from models.preflight import CodeFacts
from models.skill_map import Component, SkillMap

_FINDING_COUNTER = 0


def _next_id() -> str:
    global _FINDING_COUNTER
    _FINDING_COUNTER += 1
    return f"HC-{_FINDING_COUNTER:03d}"


def _components_of_type(skill_map: SkillMap, t: str) -> list[Component]:
    return [c for c in skill_map.components if c.component_type == t]


def _extract_schema_params(component: Component) -> Optional[list[dict]]:
    """
    Try to extract a parameter list from a schema component.
    Handles JSON Schema style and simple key-value descriptions.
    """
    content = component.content.strip()

    # Try JSON parse first
    try:
        data = json.loads(content)
        # JSON Schema style: {properties: {param: {type: ..., description: ...}}}
        if "properties" in data:
            params = []
            required = data.get("required", [])
            for name, schema in data["properties"].items():
                params.append({
                    "name": name,
                    "type": schema.get("type", "unknown"),
                    "required": name in required,
                    "description": schema.get("description", ""),
                })
            return params
        # Flat list style: [{name, type, required, description}]
        if isinstance(data, list) and data and "name" in data[0]:
            return data
    except (json.JSONDecodeError, KeyError):
        pass

    # Try YAML-style or markdown table extraction (best-effort).
    # Column order is taken from the header row: writing `| type | name | ... |`
    # must not be read as a parameter called "type".
    params = []
    header: Optional[list[str]] = None
    for raw in content.splitlines():
        line = raw.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip().strip("`*") for c in line.strip("|").split("|")]
        if not cells:
            continue
        # Separator row: | --- | :---: | ...
        if all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        row = dict(zip(header, cells))
        name = row.get("name") or row.get("param") or row.get("parameter") or row.get("flag")
        if not name:
            continue
        # Drop placeholder rows and anything that is obviously not an identifier.
        if name.startswith("<") or name.startswith("-"):
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", name):
            continue
        req_raw = (row.get("required") or row.get("req") or "").lower()
        params.append({
            "name": name,
            "type": (row.get("type") or row.get("类型") or "unknown"),
            "required": req_raw in ("yes", "true", "required", "y", "是", "必填"),
            "description": row.get("description") or row.get("说明") or "",
        })
    return params if params else None


# Type compatibility table (non-strict mode)
_COMPAT_TYPES: dict[str, set[str]] = {
    "int": {"int", "integer", "number", "float"},
    "float": {"float", "number", "int", "integer"},
    "str": {"str", "string"},
    "bool": {"bool", "boolean"},
    "list": {"list", "array"},
    "dict": {"dict", "object"},
}


def _types_compatible(schema_type: str, code_type: Optional[str], strict: bool) -> bool:
    if code_type is None:
        return True  # no annotation — can't confirm mismatch
    s = schema_type.lower()
    c = code_type.lower()
    if s == c:
        return True
    if not strict:
        return c in _COMPAT_TYPES.get(s, {s})
    return False


def _select_target_function(skill_map: SkillMap, code_facts: CodeFacts) -> tuple[Optional[dict], str]:
    """Pick the implementation function a parameter schema should be compared to.

    Never falls back to "any function": doing that produced a comparison between
    a documented parameter list and an unrelated helper, so the diff was noise.
    Returns (function, how_it_was_chosen) or (None, reason_it_could_not_be).
    """
    # A zero-argument entry point (e.g. `app()`) cannot be what a parameter
    # table documents, so only candidates that take parameters are eligible.
    with_args = [f for f in code_facts.functions if f["params"]]
    by_name = {f["name"]: f for f in with_args}
    if not by_name:
        return None, "no implementation function taking parameters was parsed"

    # 1. Evidence: a parameterised function called under `__main__`.
    for name in code_facts.module_entry_calls:
        if name in by_name:
            return by_name[name], f"module __main__ calls {name}()"

    # 2. Rank by parameter-name overlap with the schema (names matching is
    #    evidence; a name coincidence is not).
    schema_names: set[str] = set()
    for comp in _components_of_type(skill_map, "parameter_schema"):
        for p in (_extract_schema_params(comp) or []):
            schema_names.add(p["name"])
    ranked = sorted(
        ((len(schema_names & {p["name"] for p in f["params"]}), f) for f in with_args),
        key=lambda t: -t[0],
    )
    if ranked and ranked[0][0] > 0:
        hits, fn = ranked[0]
        return fn, f"best parameter-name overlap with the schema ({hits} shared name(s))"

    # 3. The parser's entry guess, if it takes parameters.
    if code_facts.entry_function in by_name:
        return by_name[code_facts.entry_function], f"entry function {code_facts.entry_function}()"

    return None, "could not determine which function the schema documents"


def compare(skill_map: SkillMap, code_facts: CodeFacts, strict_type_match: bool = True) -> tuple[list[Finding], str]:
    """
    Compare parameter_schema components against CodeFacts function signatures.
    Returns (findings, diff_summary_text).
    """
    findings: list[Finding] = []
    diff_lines: list[str] = []

    schema_components = _components_of_type(skill_map, "parameter_schema")
    if not schema_components:
        return findings, ""
    if not code_facts.functions:
        return findings, "[schema_comparator] No implementation functions parsed — schema comparison skipped."

    target_func, how = _select_target_function(skill_map, code_facts)
    if target_func is None:
        # Explicitly reported instead of silently producing nothing.
        return findings, f"[schema_comparator] {len(schema_components)} schema component(s) not compared: {how}."

    code_param_names = {p["name"] for p in target_func["params"]}
    code_param_map = {p["name"]: p for p in target_func["params"]}

    for schema_comp in schema_components:
        schema_params = _extract_schema_params(schema_comp)
        if schema_params is None:
            diff_lines.append(f"[{schema_comp.source_file}] Could not parse schema — LLM review needed.")
            continue

        # A schema whose names share nothing with the target function is most
        # likely a different interface, not N missing parameters. Reporting
        # every one of them as "over-promised" is what made this checker noisy.
        schema_param_names = {p["name"] for p in schema_params}
        if not (schema_param_names & code_param_names):
            diff_lines.append(
                f"[{schema_comp.source_file}] No overlapping parameter names with "
                f"{target_func['name']}() — not compared (possible interface mismatch, needs LLM review)."
            )
            continue
        diff_lines.append(f"[{schema_comp.source_file}] compared against {target_func['name']}() ({how})")

        # 1. Schema declares params not in code
        for p in schema_params:
            if p["name"] not in code_param_names:
                diff_lines.append(f"OVER-PROMISED param '{p['name']}': in schema but not in code function '{target_func['name']}'")
                findings.append(Finding(
                    id=_next_id(),
                    taxonomy_l1="implementation",
                    taxonomy_l2="over_promised",
                    taxonomy_l3="missing_parameter",
                    severity="high",
                    agent_impact=AgentImpact(
                        blocks_execution=False,
                        produces_silent_error=True,
                        impact_description=f"Schema declares parameter '{p['name']}' but implementation '{target_func['name']}' does not accept it.",
                        impact_class="may_block_if",
                    ),
                    evidence_a=EvidenceSpan(
                        file=schema_comp.source_file,
                        line_start=schema_comp.source_span[0] if schema_comp.source_span else None,
                        line_end=schema_comp.source_span[1] if schema_comp.source_span else None,
                        span_text=f"Schema declares parameter: {p['name']} ({p.get('type', 'unknown')})",
                    ),
                    evidence_b=EvidenceSpan(
                        file=target_func.get("source_file", "impl"),
                        line_start=target_func.get("lineno"),
                        line_end=None,
                        span_text=f"Function '{target_func['name']}' params: {[p['name'] for p in target_func['params']]}",
                    ),
                    rationale=f"Parameter '{p['name']}' is declared in the schema but absent from the code implementation.",
                    validation_status="hard_rule",
                    source_checker="schema_comparator",
                    confidence="verified",
                ))

        # 2. Code has params not in schema (under-promised)
        for p in target_func["params"]:
            if p["name"] not in schema_param_names:
                diff_lines.append(f"UNDER-PROMISED param '{p['name']}': in code but not in schema")
                findings.append(Finding(
                    id=_next_id(),
                    taxonomy_l1="implementation",
                    taxonomy_l2="under_promised",
                    taxonomy_l3="implicit_param_support",
                    severity="low",
                    agent_impact=AgentImpact(
                        blocks_execution=False,
                        produces_silent_error=False,
                        impact_description=f"Parameter '{p['name']}' is supported by code but not documented. Agent cannot leverage it.",
                        impact_class="cosmetic",
                    ),
                    evidence_a=EvidenceSpan(
                        file=target_func.get("source_file", "impl"),
                        line_start=target_func.get("lineno"),
                        line_end=None,
                        span_text=f"Function '{target_func['name']}' has undocumented param: {p['name']}",
                    ),
                    evidence_b=None,
                    rationale=f"Parameter '{p['name']}' exists in code but is absent from the schema. Benign — agent simply cannot use it.",
                    validation_status="hard_rule",
                    source_checker="schema_comparator",
                    confidence="verified",
                ))

        # 3. Type mismatches for shared params
        for p in schema_params:
            if p["name"] in code_param_map:
                code_p = code_param_map[p["name"]]
                if not _types_compatible(p.get("type", ""), code_p.get("type"), strict_type_match):
                    diff_lines.append(f"TYPE MISMATCH param '{p['name']}': schema={p.get('type')} code={code_p.get('type')}")
                    findings.append(Finding(
                        id=_next_id(),
                        taxonomy_l1="implementation",
                        taxonomy_l2="over_promised",
                        taxonomy_l3="missing_parameter",
                        severity="high",
                        agent_impact=AgentImpact(
                            blocks_execution=False,
                            produces_silent_error=True,
                            impact_description=f"Type mismatch for '{p['name']}': schema says {p.get('type')}, code expects {code_p.get('type')}.",
                            impact_class="may_block_if",
                        ),
                        evidence_a=EvidenceSpan(
                            file=schema_comp.source_file,
                            line_start=None,
                            line_end=None,
                            span_text=f"Schema: {p['name']}: {p.get('type')}",
                        ),
                        evidence_b=EvidenceSpan(
                            file=target_func.get("source_file", "impl"),
                            line_start=target_func.get("lineno"),
                            line_end=None,
                            span_text=f"Code: {p['name']}: {code_p.get('type')}",
                        ),
                        rationale=f"Parameter '{p['name']}' has type '{p.get('type')}' in schema but '{code_p.get('type')}' in code.",
                        validation_status="hard_rule",
                        source_checker="schema_comparator",
                        confidence="verified",
                    ))

    diff_summary = "\n".join(diff_lines)
    return findings, diff_summary

