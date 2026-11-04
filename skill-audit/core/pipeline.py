from __future__ import annotations

import asyncio
import json
from pathlib import Path

from comprehension.scanner import scan, SkillRootError, validate_skill_root
from comprehension.comprehension_agent import (
    run_comprehension, skill_cache_key, skill_map_to_cache, skill_map_from_cache,
    validate_skill_map, ComprehensionError,
)
from core.config import Config
from core.aggregator import aggregate
from hard_checkers import code_parser, schema_comparator, url_validator, env_constraint_checker
from llm_checkers.env_layer_checker import EnvLayerChecker
from llm_checkers.doc_layer_checker import DocLayerChecker
from llm_checkers.impl_over_promised_checker import ImplOverPromisedChecker
from llm_checkers.impl_semantic_conflict_checker import ImplSemanticConflictChecker
from llm_checkers.impl_under_promised_checker import ImplUnderPromisedChecker
from llm_client.factory import build_llm_client
from models.finding import Finding
from models.preflight import PreflightData
from report.reporter import build_report
from report.md_reporter import build_md_report
from validator.criticality_validator import validate
from core.aggregator import root_cause_stats


class Pipeline:
    def __init__(self, config: Config, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        # In dry-run mode no credentials are needed: only the deterministic
        # checkers run, which is enough to exercise and regression-test them.
        self.llm_client = None if dry_run else build_llm_client(config.llm)
        self.validator_client = None if dry_run else build_llm_client(config.validator)

    async def run(self, skill_dir: str) -> dict:
        cfg = self.config

        # ── Phase 1: Scan ─────────────────────────────────────────────────────
        print("[1/7] Scanning skill directory...")
        skill_dir = validate_skill_root(skill_dir)
        entries = scan(skill_dir, first_lines_count=cfg.comprehension.first_lines_count)
        print(f"      {len(entries)} files found.")

        # ── Phase 2: Comprehension ────────────────────────────────────────────
        skill_map = None
        cache_file = None
        if cfg.pipeline.cache_dir:
            cache_dir = Path(cfg.pipeline.cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            # The report and the cache itself may live inside the audited
            # directory; exclude them so the key stays a function of the skill
            # content only (otherwise the second run always missed the cache).
            out_path = Path(cfg.report.output_path).resolve()
            excl = [str(out_path), str(out_path.with_suffix('.md')), str(cache_dir.resolve())]
            cache_file = cache_dir / (skill_cache_key(skill_dir, exclude=excl) + '.json')
            if cache_file.exists():
                try:
                    cached = skill_map_from_cache(json.loads(cache_file.read_text()))
                    # Poisoned entries: the old silent JSON fallback cached a map
                    # with files_read but no components. Trusting it makes the
                    # audit report "0 findings" forever, so re-run instead.
                    if cached.files_read and not cached.components:
                        raise ComprehensionError(
                            "cached map has files_read but 0 components "
                            "(written by the pre-fix silent JSON fallback)")
                    skill_map = cached
                    print(f"[2/7] Comprehension cache hit: {cache_file.name}")
                except Exception as exc:                      # noqa: BLE001
                    print(f"      cache unusable ({exc}); recomputing")
                    skill_map = None
        if skill_map is None and self.dry_run:
            # No cache and no LLM: fall back to a coarse map built from the
            # files, so the deterministic checkers still have something real to
            # work on instead of silently producing nothing.
            from core.heuristic_map import build_heuristic_map
            skill_map = build_heuristic_map(skill_dir, cfg.comprehension.first_lines_count)
            print("[2/7] Comprehension skipped (dry-run) — heuristic map used instead.")
        if skill_map is None:
            print("[2/7] Running Comprehension Agent (2-round LLM)...")
            skill_map = await run_comprehension(skill_dir, entries, self.llm_client, cfg.comprehension)
        # Never let an untrustworthy map reach the checkers or the cache.
        validate_skill_map(skill_map)
        if cache_file is not None:
            cache_file.write_text(json.dumps(skill_map_to_cache(skill_map), ensure_ascii=False))
        print(f"      {len(skill_map.components)} components identified, "
              f"{len(skill_map.sub_skills)} sub-skills, "
              f"{len(skill_map.files_read)} files read in full.")

        # ── Phase 3: Hard Checks ──────────────────────────────────────────────
        print("[3/7] Running hard-rule checkers...")

        # code_parser must run first (others depend on CodeFacts)
        code_facts = code_parser.parse(skill_map)

        # schema_comparator depends on code_facts
        schema_findings, diff_summary = schema_comparator.compare(
            skill_map, code_facts,
            strict_type_match=cfg.hard_checkers.schema_strict_type_match,
        )

        # env_constraint_checker is sync; url_validator is async
        env_findings: list[Finding] = env_constraint_checker.check(skill_map, code_facts)
        if cfg.pipeline.run_url_validation:
            url_findings = await url_validator.validate(
                skill_map,
                timeout_seconds=cfg.hard_checkers.url_timeout_seconds,
                max_concurrent=cfg.hard_checkers.url_max_concurrent,
                mode=cfg.hard_checkers.url_mode,
                code_urls=code_facts.http_urls,
            )
        else:
            url_findings = []

        hard_findings = schema_findings + env_findings + url_findings
        print(f"      {len(hard_findings)} hard-rule findings.")

        preflight = PreflightData(
            skill_map=skill_map,
            code_facts=code_facts,
            hard_findings=hard_findings,
            schema_diff_summary=diff_summary,
        )

        # ── Phase 4: LLM Checkers ─────────────────────────────────────────────
        skip = set(cfg.pipeline.skip_checkers)

        all_checkers = [
            EnvLayerChecker(self.llm_client),
            DocLayerChecker(self.llm_client),
            ImplOverPromisedChecker(self.llm_client),
            ImplSemanticConflictChecker(self.llm_client),
            ImplUnderPromisedChecker(self.llm_client),
        ]
        active_checkers = [c for c in all_checkers if c.checker_name not in skip]

        llm_findings: list[Finding] = []
        checker_results: list = []
        if self.dry_run:
            print("[4/7] LLM checkers skipped (dry-run).")
        elif cfg.pipeline.parallel_llm_checkers:
            checker_results = await asyncio.gather(
                *[c.run(preflight) for c in active_checkers],
                return_exceptions=True,
            )
        else:
            for c in active_checkers:
                try:
                    checker_results.append(await c.run(preflight))
                except Exception as e:
                    print(f"      WARNING: {c.checker_name} failed: {e}")
                    checker_results.append([])

        for i, result in enumerate(checker_results):
            if isinstance(result, Exception):
                print(f"      WARNING: {active_checkers[i].checker_name} failed: {result}")
            else:
                llm_findings.extend(result)

        print(f"      {len(llm_findings)} LLM findings.")

        # ── Phase 5: Validation ───────────────────────────────────────────────
        if self.dry_run or not llm_findings:
            print("[5/7] Validator skipped (no LLM findings).")
            validated_findings = list(llm_findings)
        else:
            print("[5/7] Running criticality validator (batched)...")
            validated_findings = await validate(
                llm_findings, preflight, self.validator_client,
                report_under_promised=cfg.pipeline.report_under_promised,
            )
        suppressed = sum(1 for f in validated_findings if f.validation_status == "suppressed")
        print(f"      {suppressed} findings suppressed.")

        # ── Phase 6: Aggregate ────────────────────────────────────────────────
        print("[6/7] Aggregating and deduplicating findings...")
        final_findings = aggregate(
            hard_findings,
            validated_findings,
            include_suppressed=cfg.report.include_suppressed,
        )
        print(f"      {len(final_findings)} final findings.")

        # ── Token usage summary ───────────────────────────────────────────────
        empty = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        auditor_usage = self.llm_client.usage_summary() if self.llm_client else dict(empty)
        validator_usage = self.validator_client.usage_summary() if self.validator_client else dict(empty)
        token_summary = {
            "auditor": auditor_usage,
            "validator": validator_usage,
            "total_calls": auditor_usage["calls"] + validator_usage["calls"],
            "total_input_tokens": auditor_usage["input_tokens"] + validator_usage["input_tokens"],
            "total_output_tokens": auditor_usage["output_tokens"] + validator_usage["output_tokens"],
            "total_tokens": auditor_usage["total_tokens"] + validator_usage["total_tokens"],
        }
        print(f"      Token usage — input: {token_summary['total_input_tokens']:,}  "
              f"output: {token_summary['total_output_tokens']:,}  "
              f"total: {token_summary['total_tokens']:,}  "
              f"calls: {token_summary['total_calls']}")

        # ── Phase 7: Build report ─────────────────────────────────────────────
        print("[7/7] Building report...")
        report = build_report(
            skill_dir=skill_dir,
            skill_map=skill_map,
            findings=final_findings,
            auditor_model=cfg.llm.model,
            validator_model=cfg.validator.model,
        )
        report["token_usage"] = token_summary
        report["summary"].update(root_cause_stats(final_findings))
        report["summary"]["raw_finding_count"] = len(hard_findings) + len(llm_findings)
        report["summary"]["suppressed_by_rule"] = sum(
            1 for f in llm_findings if f.validation_status == "suppressed")
        report["preflight"] = {
            "entry_function": code_facts.entry_function,
            "module_entry_calls": code_facts.module_entry_calls,
            "functions_parsed": len(code_facts.functions),
            "schema_diff": (preflight.schema_diff_summary or "")[:2000],
            "hard_findings_by_checker": _count_by_checker(hard_findings),
            "dry_run": self.dry_run,
        }

        # ── MD report ─────────────────────────────────────────────────────────
        md_path = cfg.report.output_path.replace(".json", ".md")
        Path(md_path).parent.mkdir(parents=True, exist_ok=True)
        md_content = build_md_report(
            skill_dir=skill_dir,
            skill_map=skill_map,
            findings=final_findings,
            auditor_model=cfg.llm.model,
            validator_model=cfg.validator.model,
            token_usage=token_summary,
            audit_time=report["meta"]["audit_time"],
        )
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"      MD report: {md_path}")

        return report


def _count_by_checker(findings: list[Finding]) -> dict:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.source_checker] = counts.get(f.source_checker, 0) + 1
    return counts
