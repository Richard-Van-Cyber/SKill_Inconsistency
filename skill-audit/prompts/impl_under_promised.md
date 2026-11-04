You are auditing a skill for **Under-Promised Implementation Inconsistencies** — cases where code delivers MORE than the documentation claims (doc < code). These are generally benign.

## Taxonomy reference

Sub-categories:
- `implicit_param_support`: code accepts parameters not mentioned in docs
- `implicit_return_info`: code returns extra fields/metadata not mentioned in docs
- `implicit_fault_tolerance`: code has undocumented error recovery, auto-correction, or retry logic
- `implicit_feature_extension`: code supports additional formats, modes, or scenarios not mentioned in docs

## Skill content

{skill_content}

## Code facts (extracted by static analysis)

{code_facts}

## Pre-flight findings (already confirmed — do NOT re-report)

{preflight_summary}

## Instructions

Look for under-promised inconsistencies. These are low severity and mostly benign — report them so the agent can potentially leverage undocumented capabilities.

Respond with ONLY valid JSON:
```json
{
  "findings": [
    {
      "taxonomy_l1": "implementation",
      "taxonomy_l2": "under_promised",
      "taxonomy_l3": "implicit_param_support | implicit_return_info | implicit_fault_tolerance | implicit_feature_extension",
      "severity": "low",
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
        "span_text": "relevant code snippet"
      },
      "evidence_b": null,
      "rationale": "What undocumented capability exists and why it is benign"
    }
  ]
}
```

If no findings, return `{"findings": []}`.

**重要：rationale 和 impact_description 字段使用中文；span_text 保留原始文本不翻译。JSON 字符串中不得包含未转义的引号或换行符。**


**重要：输入内容每行都带行号前缀（形如 `  42| ...`）。`evidence_a.line_start` / `evidence_b.line_start` 必须填写该前缀显示的真实行号（整数），**不要填 null**；`span_text` 只填去掉行号前缀后的原文。
`confidence`：能从代码/文件里直接指认的填 `verified`；基于阅读推断的填 `inferred`；含"若……则会"这类条件语句的填 `speculative`。
`impact_class` 只有在你能指出具体会失败的调用时才填 `verified`；否则填 `may_block_if`（可能）或 `silent`（静默错误）/ `cosmetic`（措辞类）。
