You are auditing a skill for **Semantically Conflicting Implementation Inconsistencies** — cases where both the documentation and code define something, but their meanings are fundamentally opposite or contradictory (doc ≠ code).

## Taxonomy reference

Sub-categories:
- `semantic_param_conflict`: a parameter's meaning, unit, format, or purpose is opposite to what the doc describes
- `semantic_return_conflict`: a return value's meaning or success/failure indicator is opposite to what the doc describes
- `side_effect_conflict`: doc claims no side effects but code modifies data/state/config, or vice versa
- `workflow_conflict`: documented execution order or preconditions are reversed in actual code logic

## Skill content

{skill_content}

## Code facts (extracted by static analysis)

{code_facts}

## Pre-flight findings (already confirmed — do NOT re-report)

{preflight_summary}

## Instructions

These are the most dangerous inconsistencies — they produce NO errors but cause completely wrong results. Look carefully for:
1. Parameters where the doc and code use the same name but opposite semantics (e.g., doc says "limit=max results" but code uses it as "offset")
2. Return values where success/failure indicators are inverted (doc: 1=success, code: 0=success)
3. Functions claimed to be read-only that actually write/modify state
4. Workflow steps that the doc says happen in order A→B but code executes B→A

Respond with ONLY valid JSON:
```json
{
  "findings": [
    {
      "taxonomy_l1": "implementation",
      "taxonomy_l2": "semantically_conflicting",
      "taxonomy_l3": "semantic_param_conflict | semantic_return_conflict | side_effect_conflict | workflow_conflict",
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
        "span_text": "exact conflicting code snippet"
      },
      "rationale": "Why the semantics are conflicting and which sub-category it belongs to"
    }
  ]
}
```

If no findings, return `{"findings": []}`.

**重要：rationale 和 impact_description 字段使用中文；span_text 保留原始文本不翻译。JSON 字符串中不得包含未转义的引号或换行符。**


**重要：输入内容每行都带行号前缀（形如 `  42| ...`）。`evidence_a.line_start` / `evidence_b.line_start` 必须填写该前缀显示的真实行号（整数），**不要填 null**；`span_text` 只填去掉行号前缀后的原文。
`confidence`：能从代码/文件里直接指认的填 `verified`；基于阅读推断的填 `inferred`；含"若……则会"这类条件语句的填 `speculative`。
`impact_class` 只有在你能指出具体会失败的调用时才填 `verified`；否则填 `may_block_if`（可能）或 `silent`（静默错误）/ `cosmetic`（措辞类）。
