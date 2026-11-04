You are auditing a skill for **Document Layer Inconsistencies** — conflicts that exist purely at the text/description level, without involving code implementation.

## Taxonomy reference

Sub-categories:
- `interface_contract_mismatch`: input/output contracts between sub-skills don't align (field names, types, structure)
- `shared_concept_definition_conflict`: the same concept, enum value, or semantic is defined differently in different places
- `cross_document_process_conflict`: workflow order, preconditions, or execution flow described differently in different places

## Skill content

{skill_content}

## Sub-skill collaboration structure (extracted by comprehension agent)

{sub_skill_relations}

## Pre-flight findings (already confirmed — do NOT re-report)

{preflight_summary}

## Instructions

Analyze the skill for document-level inconsistencies. Pay special attention to:
1. Sub-skill interfaces: does sub-skill A's declared output match sub-skill B's declared input?
2. Concept definitions: are status codes, enums, field names defined consistently across all documents?
3. Process flow: is the collaboration order described consistently everywhere?

These are the most hidden defects — they produce no error at runtime but cause completely wrong results.

Respond with ONLY valid JSON:
```json
{
  "findings": [
    {
      "taxonomy_l1": "document",
      "taxonomy_l2": "interface_contract_mismatch | shared_concept_definition_conflict | cross_document_process_conflict",
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
        "span_text": "exact quote"
      },
      "evidence_b": {
        "file": "relative/path",
        "line_start": 42,
        "line_end": 44,
        "span_text": "exact conflicting quote"
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
