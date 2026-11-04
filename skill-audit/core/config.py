from __future__ import annotations

import os
import yaml
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: Optional[str]
    temperature: float
    max_tokens: int


@dataclass
class ComprehensionConfig:
    first_lines_count: int
    max_file_size_kb: int


@dataclass
class PipelineConfig:
    parallel_llm_checkers: bool
    run_url_validation: bool
    report_under_promised: bool
    skip_checkers: list[str]
    cache_dir: Optional[str] = None     # comprehension cache (same skill => same SkillMap)


@dataclass
class HardCheckerConfig:
    url_timeout_seconds: int
    url_max_concurrent: int
    schema_strict_type_match: bool
    # off | lenient | strict — see hard_checkers/url_validator.validate
    url_mode: str = "lenient"


@dataclass
class ReportConfig:
    output_path: str
    include_suppressed: bool


@dataclass
class Config:
    llm: LLMConfig
    validator: LLMConfig
    comprehension: ComprehensionConfig
    pipeline: PipelineConfig
    hard_checkers: HardCheckerConfig
    report: ReportConfig


def _resolve_env(value: str) -> str:
    """Substitute ${VAR} patterns with environment variable values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        resolved = os.environ.get(var_name)
        if not resolved:
            raise EnvironmentError(f"Required environment variable '{var_name}' is not set.")
        return resolved
    return value


def load_config(path: str) -> Config:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    def llm_from(d: dict) -> LLMConfig:
        return LLMConfig(
            provider=d["provider"],
            model=d["model"],
            api_key=_resolve_env(d["api_key"]),
            base_url=d.get("base_url"),
            temperature=d["temperature"],
            max_tokens=d["max_tokens"],
        )

    hc = raw.get("hard_checkers", {})
    return Config(
        llm=llm_from(raw["llm"]),
        validator=llm_from(raw["validator"]),
        comprehension=ComprehensionConfig(
            first_lines_count=raw["comprehension"]["first_lines_count"],
            max_file_size_kb=raw["comprehension"]["max_file_size_kb"],
        ),
        pipeline=PipelineConfig(
            parallel_llm_checkers=raw["pipeline"]["parallel_llm_checkers"],
            run_url_validation=raw["pipeline"]["run_url_validation"],
            report_under_promised=raw["pipeline"]["report_under_promised"],
            skip_checkers=raw["pipeline"].get("skip_checkers", []),
            cache_dir=raw["pipeline"].get("cache_dir"),
        ),
        hard_checkers=HardCheckerConfig(
            url_timeout_seconds=hc.get("url_validator", {}).get("timeout_seconds", 5),
            url_max_concurrent=hc.get("url_validator", {}).get("max_concurrent", 10),
            schema_strict_type_match=hc.get("schema_comparator", {}).get("strict_type_match", True),
            url_mode=hc.get("url_validator", {}).get("mode", "lenient"),
        ),
        report=ReportConfig(
            output_path=raw["report"]["output_path"],
            include_suppressed=raw["report"]["include_suppressed"],
        ),
    )
