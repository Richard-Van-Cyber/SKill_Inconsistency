You are auditing a skill for **Over-Promised Implementation Inconsistencies** — cases where documentation claims more than the code actually delivers (doc > code).

## Taxonomy reference

Sub-categories:
- `missing_parameter`: doc declares a parameter that code does not accept, or declares wrong type/required-ness
- `missing_return_field`: doc promises a return field/structure that code does not actually return
- `unimplemented_feature`: doc describes a capability that code does not implement
- `missing_constraint_or_exception`: doc declares validation rules or exception types that code does not enforce

## Skill content

{skill_content}

## Code facts (extracted by static analysis)

{code_facts}

## Schema diff summary (parameter-level mismatches already found by static analysis)

{schema_diff}

## Pre-flight findings (already confirmed — do NOT re-report)

{preflight_summary}

## Instructions

Look for over-promised inconsistencies NOT already in the schema diff or pre-flight findings.
Focus on:
1. Feature claims in descriptions that have no corresponding code logic
2. Return value structures promised in docs that code doesn't produce
3. Validation/exception behavior promised but not implemented
4. Batch/multi-item capabilities claimed but only single-item implemented

Respond with ONLY valid JSON:
```json
{
  "findings": [
    {
      "taxonomy_l1": "implementation",
      "taxonomy_l2": "over_promised",
      "taxonomy_l3": "missing_parameter | missing_return_field | unimplemented_feature | missing_constraint_or_exception",
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
        "span_text": "exact quote from documentation"
      },
      "evidence_b": {
        "file": "relative/path",
        "line_start": 42,
        "line_end": 44,
        "span_text": "relevant code snippet showing the absence"
      },
      "rationale": "Why this is over-promised and which sub-category it belongs to"
    }
  ]
}
```

If no findings, return `{"findings": []}`.

**重要：rationale 和 impact_description 字段使用中文；span_text 保留原始文本不翻译。JSON 字符串中不得包含未转义的引号或换行符。**


**重要：输入内容每行都带行号前缀（形如 `  42| ...`）。`evidence_a.line_start` / `evidence_b.line_start` 必须填写该前缀显示的真实行号（整数），**不要填 null**；`span_text` 只填去掉行号前缀后的原文。
`confidence`：能从代码/文件里直接指认的填 `verified`；基于阅读推断的填 `inferred`；含"若……则会"这类条件语句的填 `speculative`。
`impact_class` 只有在你能指出具体会失败的调用时才填 `verified`；否则填 `may_block_if`（可能）或 `silent`（静默错误）/ `cosmetic`（措辞类）。
