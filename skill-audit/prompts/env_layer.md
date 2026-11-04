You are auditing a skill for **Environmental Layer Inconsistencies** — mismatches between the skill's declared environment assumptions and real-world conditions.

## Taxonomy reference

You must classify findings into one of these sub-categories:
- `external_resource_invalid`: URLs/endpoints referenced in docs or code are broken or removed
- `dependency_version_drift`: declared dependency versions are incompatible with actual available versions
- `external_service_contract_change`: external service input/output format, auth, or field definitions have changed
- `environment_fact_conflict`: skill's runtime assumptions conflict with actual environment constraints

## Skill content

{skill_content}

## Pre-flight findings (already confirmed by static analysis — do NOT re-report these)

{preflight_summary}

## Instructions

Analyze the skill for environmental inconsistencies NOT already covered by pre-flight findings.
Focus on:
1. Dependency declarations vs. what the code actually imports/uses
2. External service assumptions embedded in the description vs. code
3. Environment constraints declared in docs that code may violate

For each finding, respond in JSON. Respond with ONLY valid JSON:
```json
{
  "findings": [
    {
      "taxonomy_l1": "environmental",
      "taxonomy_l2": "dependency_version_drift | external_service_contract_change | external_resource_invalid | environment_fact_conflict",
      "taxonomy_l3": null,
      "severity": "critical | high | medium | low",
      "confidence": "verified | inferred | speculative",
      "agent_impact": {
        "blocks_execution": false,
        "produces_silent_error": true,
        "impact_class": "verified | may_block_if | silent | cosmetic",
        "impact_description": "..."
      },
      "evidence_a": {
        "file": "relative/path",
        "line_start": 42,
        "line_end": 44,
        "span_text": "exact quote from the file"
      },
      "evidence_b": {
        "file": "relative/path",
        "line_start": 42,
        "line_end": 44,
        "span_text": "exact quote from the conflicting location"
      },
      "rationale": "Why this is an inconsistency and which sub-category it belongs to"
    }
  ]
}
```

If no findings, return `{"findings": []}`.

**重要：rationale 和 impact_description 字段使用中文；span_text 保留原始文本不翻译。JSON 字符串中不得包含未转义的引号或换行符。**


**重要：输入内容每行都带行号前缀（形如 `  42| ...`）。`evidence_a.line_start` / `evidence_b.line_start` 必须填写该前缀显示的真实行号（整数），**不要填 null**；`span_text` 只填去掉行号前缀后的原文。
`confidence`：能从代码/文件里直接指认的填 `verified`；基于阅读推断的填 `inferred`；含"若……则会"这类条件语句的填 `speculative`。
`impact_class` 只有在你能指出具体会失败的调用时才填 `verified`；否则填 `may_block_if`（可能）或 `silent`（静默错误）/ `cosmetic`（措辞类）。
