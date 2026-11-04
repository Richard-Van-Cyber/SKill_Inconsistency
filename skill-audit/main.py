from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from core.config import load_config
from core.pipeline import Pipeline
from comprehension.scanner import SkillRootError



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Skill inconsistency auditor — LLM-driven taxonomy-based checker"
    )
    parser.add_argument("--skill-dir", required=True, help="Path to the skill directory to audit")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml (default: config.yaml)")
    parser.add_argument("--output", default=None, help="Override report output path from config")
    parser.add_argument("--no-parallel", action="store_true", help="Force serial LLM checker execution")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run only the deterministic stages (scan + hard checkers + report). "
                             "No LLM calls and no credentials required.")
    parser.add_argument("--no-cache", action="store_true", help="Ignore/write no comprehension cache")
    parser.add_argument("--allow-url-network", action="store_true",
                        help="Enable URL probing (off by default in --dry-run)")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"error: config file not found: {args.config}", file=sys.stderr)
        return 2
    except (KeyError, TypeError) as exc:
        print(f"error: config file is malformed ({exc})", file=sys.stderr)
        return 2

    if args.output:
        config.report.output_path = args.output
    if args.no_parallel:
        config.pipeline.parallel_llm_checkers = False
    if args.no_cache:
        config.pipeline.cache_dir = None
    if args.dry_run and not args.allow_url_network:
        config.pipeline.run_url_validation = False

    try:
        pipeline = Pipeline(config, dry_run=args.dry_run)
    except Exception as exc:                      # noqa: BLE001 - credentials/provider setup
        print(f"error: cannot initialise the LLM client: {exc}", file=sys.stderr)
        print("       (use --dry-run to exercise the deterministic checkers without credentials)",
              file=sys.stderr)
        return 2

    try:
        report = await pipeline.run(args.skill_dir)
    except SkillRootError as exc:
        # A bad target must fail loudly. Returning "0 findings" for a path that
        # does not exist is indistinguishable from a clean audit.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:                      # noqa: BLE001
        print(f"error: audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    output_path = Path(config.report.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    summary = report["summary"]
    print(f"Audit complete. {summary['total_findings']} root causes "
          f"({summary['critical_count']} critical, {summary['high_count']} high; "
          f"{summary.get('raw_finding_count', summary['total_findings'])} raw findings). "
          f"Report: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
