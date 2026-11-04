"""Regression tests for the audit tool's deterministic layer.

These run without credentials — they cover the paths that silently misbehaved
before (URL noise, schema mis-linking, dedup, bad skill roots) and the new
reporting fields. Run with:  python3 tests/test_regressions.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.aggregator import aggregate                      # noqa: E402
from core.heuristic_map import build_heuristic_map         # noqa: E402
from hard_checkers import code_parser, schema_comparator, url_validator  # noqa: E402
from models.finding import AgentImpact, EvidenceSpan, Finding  # noqa: E402
from models.skill_map import Component, SkillMap           # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def _finding(l2, file, line, span, sev="high", checker="llm", conf="inferred",
             blocks=False, l3=None) -> Finding:
    return Finding(
        id="T", taxonomy_l1="implementation", taxonomy_l2=l2, taxonomy_l3=l3,
        severity=sev,
        agent_impact=AgentImpact(blocks, False, "d", impact_class="may_block_if"),
        evidence_a=EvidenceSpan(file, line, line, span), evidence_b=None,
        rationale="r", validation_status="confirmed", source_checker=checker,
        confidence=conf,
    )


# ── 1. skill root validation ────────────────────────────────────────────────
print("skill root validation")
from comprehension.scanner import SkillRootError, validate_skill_root  # noqa: E402

# NOTE: "/tmp" used to be the second case here. On a machine where anything
# under /tmp happens to contain a SKILL.md (e.g. a staged copy of the task set),
# rglob finds it and "/tmp" is legitimately accepted, so the check was really
# asserting a property of the machine. Use a fresh empty directory instead.
_empty = tempfile.mkdtemp()
for bad in ("/tmp/does-not-exist-xyz", _empty):
    try:
        validate_skill_root(bad)
        check(f"rejects {bad}", False, "no exception raised")
    except SkillRootError:
        check(f"rejects {bad}", True)

with tempfile.TemporaryDirectory() as tmp:
    open(os.path.join(tmp, "SKILL.md"), "w").write("---\nname: x\n---\nbody\n")
    try:
        validate_skill_root(tmp)
        check("accepts a directory containing SKILL.md", True)
    except SkillRootError as exc:
        check("accepts a directory containing SKILL.md", False, str(exc))


# ── 2. URL classification ───────────────────────────────────────────────────
print("url classification")
runtime, reference = code_parser.classify_doc_urls(
    "See https://wiki.example.org/page for rules.\n"
    "curl -sS https://d3js.org/d3.v6.min.js -o js/d3.js\n"
)
check("prose URL is a reference", "https://wiki.example.org/page" in reference)
check("curl URL is runtime", "https://d3js.org/d3.v6.min.js" in runtime)
check("localhost is never probed", url_validator._is_example_host("http://localhost:3000") is not None)
check("example.com is never probed", url_validator._is_example_host("https://auth.example.com") is not None)
check("pem target.com is never probed", url_validator._is_example_host("http://target.com/id_rsa") is not None)
check("a real doc host is probed", url_validator._is_example_host("https://civilization.fandom.com/wiki/X") is None)

src = '"""Doc.\nSee https://docs.example.com/spec\n"""\nAPI = "https://api.real.example.net/v1"\n'
import ast  # noqa: E402
check("docstring URLs are excluded from code literals",
      code_parser._parse_http_urls(ast.parse(src)) == ["https://api.real.example.net/v1"])


# ── 3. schema comparator ────────────────────────────────────────────────────
print("schema comparator")
code = (
    "def count(input_image, object_image, threshold):\n"
    "    return 0\n"
    "\n"
    "def main():\n"
    "    return count(1, 2, 3)\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)
schema_table = (
    "| param | type | required |\n"
    "| --- | --- | --- |\n"
    "| input_image | str | yes |\n"
    "| threshold | float | yes |\n"
    "| ghost_param | int | no |\n"
)
sm = SkillMap(skill_root=".", all_files=[], files_read=[], sub_skills=[],
              sub_skill_relations=[], comprehension_notes="", components=[
                  Component("C1", "implementation", "mod.py", None, code),
                  Component("C2", "parameter_schema", "SKILL.md", (1, 5), schema_table),
              ])
facts = code_parser.parse(sm)
found, diff = schema_comparator.compare(sm, facts)
names = sorted(f.taxonomy_l2 for f in found)
over = [f for f in found if f.taxonomy_l2 == "over_promised"]
check("finds the over-promised parameter",
      [True for f in over if "ghost_param" in f.evidence_a.span_text] == [True], str([f.evidence_a.span_text for f in over]))
check("only the genuinely missing param is over-promised", len(over) == 1, str(len(over)))
# `object_image` is absent from the table, so exactly one under-promised finding
# is correct here; the bug being guarded against is flagging *every* parameter.
check("under-promised reports only the undeclared param",
      names.count("under_promised") == 1, str(names))
check("header row is not treated as a parameter",
      not any("Schema declares parameter: param" in f.evidence_a.span_text for f in found),
      str([f.evidence_a.span_text for f in found]))
check("entry point is the parameterised function", facts.entry_function == "count", str(facts.entry_function))
check("schema diff reports what it compared", "compared against" in diff, diff[:80])

# a schema that shares no names must be skipped, not reported wholesale
sm2 = SkillMap(skill_root=".", all_files=[], files_read=[], sub_skills=[],
               sub_skill_relations=[], comprehension_notes="", components=[
                   Component("C1", "implementation", "mod.py", None, code),
                   Component("C2", "parameter_schema", "SKILL.md", (1, 3),
                             "| name | type |\n| --- | --- |\n| alpha | str |\n| beta | str |\n"),
               ])
found2, diff2 = schema_comparator.compare(sm2, code_parser.parse(sm2))
check("unrelated schema is skipped, not flagged", found2 == [], f"{len(found2)} findings")


# ── 4. aggregator dedup ─────────────────────────────────────────────────────
print("aggregator")
same_anchor = [
    _finding("interface_contract_mismatch", "SKILL.md", 42, 'edges use "from"/"to"', checker="doc_layer_checker"),
    _finding("interface_contract_mismatch", "SKILL.md", 42, 'Edge serialization uses from and to keys',
             checker="impl_semantic_conflict_checker"),
]
merged_same = aggregate([], same_anchor)
check("two checkers on the same anchor collapse to one root cause",
      len(merged_same) == 1, str(len(merged_same)))
check("the other checker is recorded as a contributor",
      "impl_semantic_conflict_checker" in merged_same[0].contributing_checkers,
      str(merged_same[0].contributing_checkers))
check("a merged finding keeps the strongest severity", merged_same[0].severity == "high")

near_miss = [
    _finding("interface_contract_mismatch", "SKILL.md", 42, 'edges use from/to'),
    _finding("interface_contract_mismatch", "SKILL.md", 43, 'from/to vs source/target mismatch'),
]
check("findings at different anchors are not over-merged",
      len(aggregate([], near_miss)) == 2)

distinct = [
    _finding("interface_contract_mismatch", "SKILL.md", 42, 'edges use from/to'),
    _finding("environment_fact_conflict", "other.md", 90, "unrelated claim", sev="medium"),
]
check("different taxonomies stay separate", len(aggregate([], distinct)) == 2)

blocks_unverified = [_finding("x", "a.md", 1, "s", blocks=True, conf="inferred")]
check("unverified blocking claim is downgraded",
      not aggregate([], blocks_unverified)[0].agent_impact.blocks_execution)


# ── 5. heuristic map / dry-run path ─────────────────────────────────────────
print("heuristic map")
with tempfile.TemporaryDirectory() as tmp:
    os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
    open(os.path.join(tmp, "SKILL.md"), "w").write("# Doc\n| param | type |\n| --- | --- |\n| a | str |\n")
    open(os.path.join(tmp, "sub", "SKILL.md"), "w").write("# Sub\n")
    open(os.path.join(tmp, "run.py"), "w").write("def go(a):\n    return a\n")
    hm = build_heuristic_map(tmp)
    kinds = {c.component_type for c in hm.components}
    check("docs become description components", "description" in kinds)
    check("code becomes implementation components", "implementation" in kinds)
    check("parameter table becomes a schema component", "parameter_schema" in kinds)
    check("sub-skill directory is detected", hm.sub_skills == ["sub"], str(hm.sub_skills))

# ── 6. comprehension must fail loudly, never silently ───────────────────────
# 29 of the 87 reports in the 2026-09-23 batch carried {"components": []} because
# _extract_json swallowed a JSON parse failure, returned an empty skeleton, and
# that skeleton was cached. The report then read "0 findings" for a skill that
# was never actually analysed.
print("comprehension failure handling")
from comprehension.comprehension_agent import (                      # noqa: E402
    ComprehensionError, _extract_json, validate_skill_map,
)
from models.skill_map import SkillMap                                # noqa: E402

check("_extract_json returns None for unparseable output",
      _extract_json("I cannot help with that.") is None)
check("_extract_json returns None for truncated JSON",
      _extract_json('{"components": [{"component_id": "c1",') is None)
check("_extract_json still parses fenced JSON",
      (_extract_json('```json\n{"components": []}\n```') or {}).get("components") == [])

_collapsed = SkillMap(skill_root="/x", all_files=[], files_read=["SKILL.md"],
                      components=[], sub_skills=[], sub_skill_relations=[],
                      comprehension_notes="解析失败")
try:
    validate_skill_map(_collapsed)
    check("a map with files_read but no components is rejected", False)
except ComprehensionError:
    check("a map with files_read but no components is rejected", True)

_ok_map = SkillMap(skill_root="/x", all_files=[], files_read=["SKILL.md"],
                   components=[Component(component_id="c1", component_type="description",
                                         source_file="SKILL.md", source_span=(1, 2),
                                         content="x")],
                   sub_skills=[], sub_skill_relations=[], comprehension_notes="")
try:
    validate_skill_map(_ok_map)
    check("a populated map is accepted", True)
except ComprehensionError as exc:
    check("a populated map is accepted", False, str(exc))

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
    sys.exit(1)
print("all checks passed")
