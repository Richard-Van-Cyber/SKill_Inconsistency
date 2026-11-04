"""Integration checks that need no credentials and no network.

Covers the paths the regression suite does not: the URL checker's probe/mode
logic (httpx mocked), the batched validator, the comprehension cache round-trip,
and the full 7-stage pipeline driven by a stub LLM.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.finding import AgentImpact, EvidenceSpan, Finding  # noqa: E402
from models.skill_map import Component, SkillMap               # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def _sm(components):
    return SkillMap(skill_root=".", all_files=[], files_read=[], components=components,
                    sub_skills=[], sub_skill_relations=[], comprehension_notes="")


def _finding(l2, span, sev="high", checker="c", conf="inferred", blocks=False):
    return Finding(id="T", taxonomy_l1="implementation", taxonomy_l2=l2, taxonomy_l3=None,
                   severity=sev,
                   agent_impact=AgentImpact(blocks, False, "d", impact_class="may_block_if"),
                   evidence_a=EvidenceSpan("SKILL.md", 1, 1, span), evidence_b=None,
                   rationale="r", validation_status="confirmed", source_checker=checker,
                   confidence=conf)


# ── 1. URL checker: probe selection, modes, and blocking semantics ───────────
print("url checker (httpx mocked)")
import httpx  # noqa: E402
import hard_checkers.url_validator as uv  # noqa: E402

PROBED: list[str] = []


class _Resp:
    def __init__(self, status):
        self.status_code = status


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def head(self, url, timeout=None, follow_redirects=None):
        PROBED.append(url)
        return _Resp(404)


uv.httpx.AsyncClient = _FakeClient

skill = _sm([
    Component("D", "description", "SKILL.md", (1, 40),
              "See https://en.wikipedia.org/wiki/Special:Deadlink for background.\n"
              "curl -sS https://cdnjs.cloudflare.com/ajax/libs/d3/6.7.0/d3.min.js -o d3.js\n"
              "http://localhost:8000/healthz is the local endpoint\n"),
    Component("I", "implementation", "run.py", (1, 5),
              'URL = "https://api.github.com/repos/py-pdf/pypdf/issues/1"\n'),
])


def run(coro):
    return asyncio.run(coro)


f = run(uv.validate(skill, mode="lenient", code_urls=["https://api.github.com/repos/py-pdf/pypdf/issues/1"]))
probed = set(PROBED)
check("code URL literal is probed", "https://api.github.com/repos/py-pdf/pypdf/issues/1" in probed)
check("command-line URL is probed", "https://cdnjs.cloudflare.com/ajax/libs/d3/6.7.0/d3.min.js" in probed)
check("prose reference is NOT probed", "https://en.wikipedia.org/wiki/Special:Deadlink" not in probed)
check("localhost is NOT probed", "http://localhost:8000/healthz" not in probed)
check("code URL reports blocking", any(x.agent_impact.blocks_execution for x in f), str([x.agent_impact.blocks_execution for x in f]))
check("doc command URL does NOT block", not any(x.agent_impact.blocks_execution for x in f if "d3.min.js" in x.evidence_a.span_text))
check("doc-only URL is at most low", all(x.severity == "low" for x in f if "d3.min.js" in x.evidence_a.span_text))

PROBED.clear()
f_off = run(uv.validate(skill, mode="off"))
check("mode=off probes nothing", PROBED == [] and f_off == [])

PROBED.clear()
f_strict = run(uv.validate(skill, mode="strict", code_urls=[]))
check("mode=strict additionally probes references",
      "https://en.wikipedia.org/wiki/Special:Deadlink" in set(PROBED))
check("strict still never blocks on a doc URL",
      all(not x.agent_impact.blocks_execution for x in f_strict))

PROBED.clear()
f_ok = run(uv.validate(_sm([Component("D", "description", "SKILL.md", (1, 2),
                                      "https://your-service.internal.example/x\n")]),
                       mode="strict", code_urls=[]))
check("reserved/example hosts never reach the network", PROBED == [] and f_ok == [])


# ── 2. Validator: batching, rule suppression, keep-on-failure ───────────────
print("validator batching")
from models.preflight import PreflightData, CodeFacts  # noqa: E402
import validator.criticality_validator as cv        # noqa: E402


class _StubClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0
        self.prompts: list[str] = []

    async def complete(self, prompt, system="", temperature=None, max_tokens=None):
        self.calls += 1
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return json.dumps(self.reply) if not isinstance(self.reply, str) else self.reply


preflight = PreflightData(skill_map=skill, code_facts=CodeFacts(
    functions=[], raises=[], http_urls=[], has_file_write=False,
    has_global_mutation=False, imports=[], entry_function=None))

many = [_finding("interface_contract_mismatch", f"span {i}") for i in range(30)]
client = _StubClient({"verdicts": []})
out = run(cv.validate(many, preflight, client))
check("30 findings use 3 batched calls (12/12/6)", client.calls == 3, str(client.calls))
check("a batch with no verdicts keeps its findings",
      sum(1 for x in out if x.validation_status != "suppressed") == 30)

client2 = _StubClient({"verdicts": [{"id": "T", "verdict": "suppressed",
                                     "adjusted_severity": "low"}]})
mixed = [_finding("interface_contract_mismatch", "a"), _finding("over_promised", "b")]
out2 = run(cv.validate(mixed, preflight, client2))
check("a suppressed verdict is applied", any(x.validation_status == "suppressed" for x in out2))
check("a suppressed finding loses its blocking claim",
      all(not x.agent_impact.blocks_execution for x in out2 if x.validation_status == "suppressed"))

under = [_finding("under_promised", "u")]
client3 = _StubClient({"verdicts": []})
out3 = run(cv.validate(under, preflight, client3, report_under_promised=False))
check("under_promised is suppressed by rule, without an LLM call",
      out3[0].validation_status == "suppressed" and client3.calls == 0)

client4 = _StubClient(RuntimeError("connection reset"))
out4 = run(cv.validate([_finding("over_promised", "x")], preflight, client4))
check("an LLM failure keeps the finding (conservative)",
      out4[0].validation_status == "confirmed", out4[0].validation_status)


# ── 3. Comprehension cache round-trip ───────────────────────────────────────
print("comprehension cache")
from comprehension.comprehension_agent import (  # noqa: E402
    skill_cache_key, skill_map_from_cache, skill_map_to_cache)

with tempfile.TemporaryDirectory() as tmp:
    open(os.path.join(tmp, "SKILL.md"), "w").write("# T\n")
    k1 = skill_cache_key(tmp)
    open(os.path.join(tmp, "SKILL.md"), "w").write("# T\nmore\n")
    k2 = skill_cache_key(tmp)
    check("cache key changes when content changes", k1 != k2, f"{k1} == {k2}")

    from comprehension.scanner import scan  # noqa: E402
    from models.skill_map import FileEntry    # noqa: E402
    orig = SkillMap(skill_root=tmp, all_files=scan(tmp), files_read=["SKILL.md"],
                    components=[Component("C", "description", "SKILL.md", (1, 2), "# T")],
                    sub_skills=["pdf"], sub_skill_relations=[], comprehension_notes="n")
    restored = skill_map_from_cache(skill_map_to_cache(orig))
    check("components survive the round-trip",
          len(restored.components) == 1 and restored.components[0].source_span == (1, 2))
    check("sub_skills survive the round-trip", restored.sub_skills == ["pdf"])


# ── 4. Full pipeline with a stub LLM ────────────────────────────────────────
print("full pipeline (stub LLM)")
import llm_client.factory as factory  # noqa: E402
import core.pipeline as pipeline_mod  # noqa: E402


class _StubLLM:
    def __init__(self, tag):
        self.tag = tag
        self.calls = 0
        self.comprehension_calls = 0

    async def complete(self, prompt, system="", temperature=None, max_tokens=None):
        self.calls += 1
        if "file_listing" in prompt or ("components" in prompt and "comprehension" in system):
            self.comprehension_calls += 1
        if "files_to_read" in prompt and "file_listing" in prompt:
            return json.dumps({"files_to_read": [{"path": "SKILL.md", "reason": "r", "priority": "high"}]})
        if "components" in prompt and "comprehension" in system:
            return json.dumps({"components": [
                {"component_id": "C1", "component_type": "description", "source_file": "SKILL.md",
                 "source_span": [1, 3], "content_summary": "d"}],
                "sub_skills": [], "sub_skill_relations": [], "comprehension_notes": "stub"})
        if "verdicts" in prompt:
            return json.dumps({"verdicts": []})
        return json.dumps({"findings": [{
            "taxonomy_l1": "document", "taxonomy_l2": "interface_contract_mismatch",
            "severity": "medium", "confidence": "inferred",
            "agent_impact": {"blocks_execution": True, "produces_silent_error": True,
                             "impact_class": "may_block_if", "impact_description": "stub"},
            "evidence_a": {"file": "SKILL.md", "line_start": 2, "line_end": 2, "span_text": "stub A"},
            "evidence_b": None, "rationale": "stub"}]})

    def usage_summary(self):
        return {"calls": self.calls, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


auditor, validator = _StubLLM("a"), _StubLLM("v")
factory.build_llm_client = lambda cfg: auditor if cfg.temperature == 0.1 else validator
pipeline_mod.build_llm_client = factory.build_llm_client

from core.config import load_config  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    open(os.path.join(tmp, "SKILL.md"), "w").write("# T\nbody\nmore\n")
    cfg = load_config("config.yaml")
    # Reports go outside the audited directory: writing them inside it changes
    # the directory content and therefore the cache key.
    os.makedirs(os.path.join(tmp, "out"), exist_ok=True)
    cfg.report.output_path = os.path.join(tmp, "out", "r.json")
    cfg.pipeline.cache_dir = os.path.join(tmp, "cache")
    cfg.pipeline.run_url_validation = False
    report = run(pipeline_mod.Pipeline(cfg).run(tmp))
    check("pipeline returns a report", isinstance(report, dict) and "summary" in report)
    check("root_cause stats are present", "root_causes" in report["summary"])
    check("preflight block is present", report.get("preflight", {}).get("dry_run") is False)
    check("an unverified blocking claim was downgraded",
          not report["findings"][0]["agent_impact"]["blocks_execution"])
    # Second run must hit the comprehension cache: the two comprehension calls
    # disappear while the LLM checkers still run against the cached SkillMap.
    before_comp = auditor.comprehension_calls
    before_total = auditor.calls
    cfg.report.output_path = os.path.join(tmp, "out", "r.json")  # same path as run 1
    run(pipeline_mod.Pipeline(cfg).run(tmp))
    check("second run makes no comprehension calls",
          auditor.comprehension_calls == before_comp,
          f"comprehension {before_comp} -> {auditor.comprehension_calls}")
    check("second run still runs the LLM checkers",
          auditor.calls > before_total)

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
    sys.exit(1)
print("all integration checks passed")
