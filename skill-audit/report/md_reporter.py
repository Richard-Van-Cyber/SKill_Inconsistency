from __future__ import annotations

from models.finding import Finding
from models.skill_map import SkillMap


_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
}

_L1_LABEL = {
    "environmental": "环境层",
    "document": "文档层",
    "implementation": "实现层",
}


def build_md_report(
    skill_dir: str,
    skill_map: SkillMap,
    findings: list[Finding],
    auditor_model: str,
    validator_model: str,
    token_usage: dict,
    audit_time: str,
) -> str:
    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    skill_name = skill_dir.rstrip("/").split("/")[-1]
    lines += [
        f"# Skill 不一致审计报告：{skill_name}",
        "",
        f"- **审计时间**：{audit_time}",
        f"- **Skill 目录**：`{skill_dir}`",
        f"- **审计模型**：{auditor_model}",
        f"- **校验模型**：{validator_model}",
        f"- **Token 消耗**：input {token_usage['total_input_tokens']:,} / output {token_usage['total_output_tokens']:,} / total {token_usage['total_tokens']:,} （{token_usage['total_calls']} 次调用）",
        "",
    ]

    # ── Skill Map Summary ─────────────────────────────────────────────────────
    lines += [
        "## Skill 结构理解",
        "",
        f"- **文件总数**：{len(skill_map.all_files)}，完整读取：{len(skill_map.files_read)}",
        f"- **识别子 Skill**：{', '.join(skill_map.sub_skills) if skill_map.sub_skills else '无'}",
    ]
    if skill_map.sub_skill_relations:
        lines.append("- **子 Skill 协作关系**：")
        for r in skill_map.sub_skill_relations:
            lines.append(f"  - `{r.from_skill}` → `{r.to_skill}`（{r.relation_type}）：{r.description}")
    if skill_map.comprehension_notes:
        lines += ["", f"> {skill_map.comprehension_notes}", ""]
    lines.append("")

    # ── Summary ───────────────────────────────────────────────────────────────
    active = [f for f in findings if f.validation_status != "suppressed"]
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in active:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    suppressed = len(findings) - len(active)
    blocking = sum(1 for f in active if f.agent_impact.blocks_execution)
    verified_blocking = sum(
        1 for f in active if f.agent_impact.blocks_execution and f.confidence == "verified")
    silent = sum(1 for f in active if f.agent_impact.produces_silent_error)
    by_conf = {"verified": 0, "inferred": 0, "speculative": 0}
    for f in active:
        by_conf[f.confidence] = by_conf.get(f.confidence, 0) + 1

    lines += [
        "## 审计概览",
        "",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 根因数（去重后） | {len(active)} |",
        f"| 🔴 Critical | {counts['critical']} |",
        f"| 🟠 High | {counts['high']} |",
        f"| 🟡 Medium | {counts['medium']} |",
        f"| 🟢 Low | {counts['low']} |",
        f"| 证据强度 verified / inferred / speculative | "
        f"{by_conf['verified']} / {by_conf['inferred']} / {by_conf['speculative']} |",
        f"| 声称阻断执行（其中已确证） | {blocking}（{verified_blocking}） |",
        f"| 产生静默错误 | {silent} |",
        f"| 已过滤（规则 + 复核） | {suppressed} |",
        "",
        "> 只有 `confidence=verified` 且 `blocks_execution=true` 的条目才表示"
        "「已确认会导致执行失败」；其余为条件式推断，请勿据此排定修复优先级。",
        "",
    ]

    # ── Findings ──────────────────────────────────────────────────────────────
    lines += ["## 详细缺陷清单", ""]

    for f in active:
        emoji = _SEVERITY_EMOJI.get(f.severity, "⚪")
        l1 = _L1_LABEL.get(f.taxonomy_l1, f.taxonomy_l1)
        taxonomy_str = f"{l1} / {f.taxonomy_l2}"
        if f.taxonomy_l3:
            taxonomy_str += f" / {f.taxonomy_l3}"

        conf_label = {"verified": "✅ 已确证", "inferred": "🔎 推断",
                      "speculative": "❔ 条件式"}.get(f.confidence, f.confidence)
        extra = ""
        if f.contributing_checkers:
            extra = f"　（另由 {', '.join(f.contributing_checkers)} 独立报出）"
        lines += [
            f"### {f.id}　{emoji} {f.severity.upper()}　`{taxonomy_str}`　{conf_label}{extra}",
            "",
        ]

        # Agent impact
        impact_flags = []
        if f.agent_impact.blocks_execution:
            impact_flags.append("🚫 阻断执行")
        elif f.agent_impact.impact_class == "may_block_if":
            impact_flags.append("⚠️ 条件式阻断")
        if f.agent_impact.produces_silent_error:
            impact_flags.append("🔇 静默错误")
        if impact_flags:
            lines.append(f"**Agent 影响**：{' / '.join(impact_flags)}　{f.agent_impact.impact_description}")
        else:
            lines.append(f"**Agent 影响**：{f.agent_impact.impact_description}")
        lines.append("")

        # Evidence
        lines.append("**证据**：")
        ea = f.evidence_a
        loc_a = f"`{ea.file}`"
        if ea.line_start:
            loc_a += f" L{ea.line_start}" + (f"-{ea.line_end}" if ea.line_end else "")
        lines.append(f"- A（{loc_a}）：`{ea.span_text[:200]}`")
        if f.evidence_b:
            eb = f.evidence_b
            loc_b = f"`{eb.file}`"
            if eb.line_start:
                loc_b += f" L{eb.line_start}" + (f"-{eb.line_end}" if eb.line_end else "")
            lines.append(f"- B（{loc_b}）：`{eb.span_text[:200]}`")
        lines.append("")

        # Rationale
        lines += [f"**判定理由**：{f.rationale}", "", "---", ""]

    # ── Token usage detail ────────────────────────────────────────────────────
    lines += [
        "## Token 消耗明细",
        "",
        "| 角色 | 调用次数 | Input | Output | Total |",
        "|---|---|---|---|---|",
        f"| 审计模型（{auditor_model}） | {token_usage['auditor']['calls']} | {token_usage['auditor']['input_tokens']:,} | {token_usage['auditor']['output_tokens']:,} | {token_usage['auditor']['total_tokens']:,} |",
        f"| 校验模型（{validator_model}） | {token_usage['validator']['calls']} | {token_usage['validator']['input_tokens']:,} | {token_usage['validator']['output_tokens']:,} | {token_usage['validator']['total_tokens']:,} |",
        f"| **合计** | **{token_usage['total_calls']}** | **{token_usage['total_input_tokens']:,}** | **{token_usage['total_output_tokens']:,}** | **{token_usage['total_tokens']:,}** |",
        "",
    ]

    return "\n".join(lines)
