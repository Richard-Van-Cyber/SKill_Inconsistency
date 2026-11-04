# Skill 不一致审计报告：skills

- **审计时间**：2026-09-23T04:06:14.726293+00:00
- **Skill 目录**：`/workspace/skillEvaluation/fixed_skills/fix-druid-loophole-cve/environment/skills`
- **审计模型**：claude-sonnet-4-6
- **校验模型**：claude-sonnet-4-6
- **Token 消耗**：input 0 / output 0 / total 0 （0 次调用）

## Skill 结构理解

- **文件总数**：27，完整读取：27
- **识别子 Skill**：druid-cve-2021-25646, jackson-security, senior-java

> heuristic map: 16 components from 27 files (no LLM comprehension)


## 审计概览

| 指标 | 数值 |
|---|---|
| 根因数（去重后） | 1 |
| 🔴 Critical | 0 |
| 🟠 High | 0 |
| 🟡 Medium | 0 |
| 🟢 Low | 1 |
| 证据强度 verified / inferred / speculative | 0 / 0 / 1 |
| 声称阻断执行（其中已确证） | 0（0） |
| 产生静默错误 | 1 |
| 已过滤（规则 + 复核） | 0 |

> 只有 `confidence=verified` 且 `blocks_execution=true` 的条目才表示「已确认会导致执行失败」；其余为条件式推断，请勿据此排定修复优先级。

## 详细缺陷清单

### F-001　🟢 LOW　`环境层 / environment_fact_conflict`　❔ 条件式

**Agent 影响**：🔇 静默错误　A read-only/offline/cross-platform phrase appears in a document, but the sentence does not refer to this skill's own code. Likely prose, not a claim.

**证据**：
- A（`senior-java/SKILL.md` L1-604）：`# Read-only with pagination`
- B（`senior-java/scripts/api_endpoint_generator.py`）：`Code performs file writes or global state mutations (detected via AST analysis)`

**判定理由**：Rule 'readonly_side_effect_conflict': documentation asserts an environmental constraint that the implementation violates.

---

## Token 消耗明细

| 角色 | 调用次数 | Input | Output | Total |
|---|---|---|---|---|
| 审计模型（claude-sonnet-4-6） | 0 | 0 | 0 | 0 |
| 校验模型（claude-sonnet-4-6） | 0 | 0 | 0 | 0 |
| **合计** | **0** | **0** | **0** | **0** |
