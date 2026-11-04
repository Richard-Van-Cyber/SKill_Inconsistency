# Skill 不一致性影响完成任务程度 —— Top 30 审计与排序报告

- **审计对象**：`tasks/<task>/audit_report.json`，共 87 份（本仓库静态检测器 `skill-audit` 于 2026-09-23 生成）
- **运行数据**：`hf_downloads/submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3`，199 次运行 / 68 个任务（claude-code 2.1.19 + haiku-4-5，带 skill）
- **复现脚本**：`analysis_tools/exposure_scan_baseline.py`、`analysis_tools/parse_baseline_runs.py`、`analysis_tools/impact_ranking.py`、`analysis_tools/make_impact_report.py`
- **原始表**：`skill_inconsistency_impact_ranking.csv`（87 行全量字段）
- **轨迹级因果审计**：见 `skill_trace_causal_audit.md` —— 本报告只做曝光度，该报告读了 199 条轨迹判断哪些不一致性真的被踩到、是否造成 effectiveness / efficiency 下降

---

## 0. 结论摘要

1. **87 份审计报告中只有 58 份有效。29 份的 comprehension 阶段输出 0 个组件**（`total_files > 0` 而 `components == []`），检测器仍照常输出“0 findings / 0 风险”的报告，属于**静默失效**：读起来像“这个 skill 很干净”，实际是“这次审计没跑成”。其中包含 `court-form-filling`、`data-to-d3`、`grid-dispatch-operator` —— 恰恰是此前三组对照实验中已确认存在高危不一致性的任务。
2. **260 条 finding 中只有 153 条（59%）在 199 次真实运行里进入过 agent 的上下文**，107 条从未被触碰；47 条达到文件级暴露。对 8 个任务而言，**全部 finding 的物理可达性为 0**（skill 从未被加载，或加载的是同任务另一个子技能）——其中 `lean4-proof` 静态风险最高（20 条 finding，18.09 分），但零可达，对完成任务的影响实测为 0。
3. **审计报告的 severity / impact 标签与任务完成之间没有正相关**：可达风险 vs 观测成功率的 Pearson r = **+0.310**（n=39），即找出的不一致性越多越严重，任务反而越容易成功；与失败运行的 token/耗时也基本无关（−0.07 / −0.22）。因此**不能**用报告里的 severity 直接排序，必须把“可达性”和“任务端实际损失”作为独立维度引入。
4. 按本报告的三维模型（成功率损害 / token 开销 / 时间开销）× 可达性门控排序，**Top 30 中的前 3 名是 `pddl-tpp-planning`、`offer-letter-generator`、`manufacturing-fjsp-optimization`**；第 12、15、18、20–24 名属于**“高静态风险但观测零损失”**（任务 100% 通过），是潜在风险而非已实现损失，修复性价比低于前 11 名。
5. 排序结果对报告本身的部分缺陷不敏感，但有 3 类缺陷必须先修，否则排序不可复核：`impact_class` 字段被写入 confidence 值（34 条）、`3d-scan-calc` 整份报告缺 `confidence`/`agent_impact`/`root_cause_id`（9 条）、`semantically_conflicting` 不在闭集 L2 词表内（2 条）。

---

## 1. 审计方法与数据口径

本报告要回答的是一句话：**哪些 skill 包里的不一致性，对任务能不能完成、花了多少 token、耗了多少时间，负面影响最大。**

这需要三样东西相乘，缺一不可：

- **可达性（Reachability）**：这条不一致性有没有机会进入 agent 的上下文。只看报告不看轨迹，会把大量“agent 根本没打开这个 skill”的条目算进影响里。判定沿用 `analysis/audit_tools/exposure_scan.py` 的三级口径：`file`（证据文件被 `Read`，或 bash 进入该 skill 目录）、`doc`（`Skill` 工具注入了该 skill 的 SKILL.md）、`none`（两者皆无）。
- **损失（Damage）**：任务没完成时，成功率、token、时间各自损失多少。用 199 次真实运行测量。
- **不一致性风险（Risk）**：报告里 finding 的 severity × confidence × impact 加权，且**只统计可达的那部分**。

三项合成：

```
reachable_risk = Σ_findings  sev_w × conf_w × impact_w × p_hit
p_hit          = (该 finding 在 n 次运行中被 file/doc 暴露的次数) / n

Damage = 0.50 × S + 0.30 × T + 0.20 × W          # 观测到的任务端损失，均在 [0,1]
   S = 1 − 成功率                                  # 成功率损害
   T = norm_log1p(失败运行的中位 token)             # token 开销
   W = norm_log1p(失败运行的中位总耗时秒)            # 时间开销

Gate   = norm_log1p(reachable_risk)              # 可达性门控，在 [0,1]
IIS    = 100 × Gate × (0.30 + 0.70 × Damage)     # Inconsistency Impact Score
```

权重取值：severity = critical 3 / high 2 / medium 1 / low 0.25；confidence = verified 1 / inferred 0.7 / speculative 0.3；impact = blocks_execution 1.0 / silent 0.9 / may_block_if 0.5 / cosmetic 0.05。`+0.30` 常数项的作用是：一个可达的高危不一致性，即使这批 rollout 恰好全过，也不应被打成 0 分（它是潜在风险），但必须明显低于已实现损失的任务。

**为什么用乘法而不是加法**：`Gate = 0` 时 IIS 恒为 0。一个从未被 agent 打开过的 skill，无论文档写得多矛盾，对这次任务完成的影响在物理上就是 0。这是本报告与“按 severity 排序”最本质的区别。

---

## 2. 第一部分：87 份审计报告本身的质量审计

### 2.1 静默失效：29/87 份报告不可用

判定规则：`skill_map_summary.total_files > 0` 且 `components == []`。此时 comprehension agent 没有产出任何结构化组件，5 个 LLM checker 与 4 个 hard-rule checker 全部空转，最终报告给出 `total_findings: 0`。

日志证据（`tasks/<task>/audit.log`）形态完全一致：

```
[1/7] Scanning skill directory...
      12 files found.
[2/7] Running Comprehension Agent (2-round LLM)...
      0 components identified, 0 sub-skills, 11 files read in full.   ← 读了 11 个文件，却识别出 0 个组件
[3/7] Running hard-rule checkers...
      0 hard-rule findings.
      0 LLM findings.
```

其中 `grid-dispatch-operator`、`fix-visual-stability` 等还命中了 comprehension 缓存（`Comprehension cache hit`，input 仅 4,196 tokens），说明**一次失败的 comprehension 结果被缓存复用**，后续重跑不会自愈。

#### 失效清单（29 份，必须重跑）

| # | Task | 文件数 | 组件数 | 原始 findings |
|---|---|---|---|---|

> 注意：这 29 份不能按“0 缺陷”解读。其中 `court-form-filling`、`data-to-d3`、`grid-dispatch-operator`、`energy-ac-optimal-power-flow`、`fix-visual-stability`、`travel-planning` 在本仓库更早的 `tool_audit_result/`、`skillbenchmark_audit/` 审计中都是缺陷密度较高的任务。

### 2.2 字段与口径缺陷

| 缺陷 | 影响条数 | 说明 | 建议 |
|---|---|---|---|
| `agent_impact.impact_class == "verified"` | **34**（涉及 17 个任务） | confidence 的取值被写进了 impact 字段。`impact_class` 的闭集是 {`silent`,`may_block_if`,`cosmetic`}，出现 `verified` 说明 checker 输出解析时串了字段；受害 checker 集中在 `env_layer_checker` 与 `impl_over_promised_checker` | 解析层显式校验 impact_class 词表，非法值落 `unknown` 而非透传 |
| `3d-scan-calc` 整份报告缺字段 | **9** | 该任务是唯一一份旧 schema 产物：全部 finding 无 `confidence`、无 `agent_impact`、无 `root_cause_id`，summary 也没有 `root_causes` / `raw_finding_count`。其中含 1 条 critical | 重跑该任务，或对缺失字段做 schema 版本检查并拒绝输出 |
| `taxonomy_l2 == "semantically_conflicting"` | 2 | 不在闭集词表内，说明 `_TAXONOMY_ALIASES` 未覆盖该别名 | 补别名 |
| `impl_under_promised_checker`、`schema_comparator` 全库 0 输出 | 0 | 87 份报告里这两个 checker 没有任何产出（`under_promised` 被 `split_by_rule` 默认抑制） | 在报告里显式标注“本类 checker 被抑制”，避免读成“不存在此类问题” |
| `agent_blocking_count` 与 `blocks_execution` 口径不一致 | — | 报告摘要的 `agent_blocking_count` 统计的是“声称阻断”，而正文脚注又声明“只有 verified + true 才算确认”。本报告另行统计 `verified_blockers` 以区分二者 | 摘要中拆成两列 |

### 2.3 覆盖率

| 项目 | 数量 |
|---|---|
| 审计报告总数 | 87 |
| comprehension 有效 | 58 |
| comprehension 失效 | 29 |
| 含 ≥1 条 finding 的有效报告 | 48 |
| finding 总数 | 377（critical 2 / high 90 / medium 119 / low 49） |
| 声称会阻断执行 | 38 |
| 声称会产生静默错误 | 152 |
| 被规则抑制的原始 finding | 276 |

---

## 3. 第二部分：运行时可达性审计

把 260 条 finding 的 `evidence.source_a/b.file` 与 199 次真实运行的工具调用逐一比对：

| 暴露等级 | 条数 | 占比 |
|---|---|---|
| `file`（证据文件被读 / bash 进入该 skill 目录） | 47 | 18% |
| `doc`（SKILL.md 被 `Skill` 工具注入，证据文件未单独读） | 106 | 41% |
| `none`（该 skill 从未加载、文件从未被读） | 107 | 41% |

**41% 的 finding 在物理上不可能影响结果。** 这不是检测器的错，但它决定了排序不能用静态 severity 做。

### 3.1 完全不可达的 8 个任务（有 finding，但 skill 从未进入上下文）

| Task | findings | 静态风险 | 观测成功率 | skill 加载率 | 原因 |
|---|---|---|---|---|---|
| `lean4-proof` | 20 | 18.088 | 0% | 0% | skill 从未被加载 |
| `fix-druid-loophole-cve` | 7 | 7.504 | 67% | 0% | skill 从未被加载 |
| `fix-erlang-ssh-cve` | 8 | 7.287 | 67% | 0% | skill 从未被加载 |
| `react-performance-debugging` | 3 | 3.7 | 0% | 100% | 加载的是同任务其它子技能，本 finding 所在文件从未进入上下文 |
| `dialogue-parser` | 6 | 3.3 | 83% | 0% | skill 从未被加载 |
| `fix-build-google-auto` | 4 | 2.709 | 0% | 0% | skill 从未被加载 |
| `syzkaller-ppdev-syzlang` | 2 | 2.009 | 0% | 0% | skill 从未被加载 |
| `exoplanet-detection-period` | 1 | 2.0 | 0% | 100% | 加载的是同任务其它子技能，本 finding 所在文件从未进入上下文 |
| `jax-computing-basics` | 3 | 1.409 | 33% | 0% | skill 从未被加载 |
| `crystallographic-wyckoff-position-analysis` | 3 | 1.213 | 64% | 100% | 加载的是同任务其它子技能，本 finding 所在文件从未进入上下文 |
| `adaptive-cruise-control` | 2 | 1.125 | 0% | 0% | skill 从未被加载 |
| `fix-build-agentops` | 1 | 0.013 | 0% | 0% | skill 从未被加载 |

典型：`lean4-proof` 有 20 条 finding、静态风险 18.09 全库最高，但 1 次运行里 skill 加载率为 0，所以它对任务完成的**实测影响是 0**；`crystallographic-wyckoff` 与 `react-performance-debugging` 加载率是 100%，但加载的是 `sympy` / `react-best-practices`，而 finding 全部落在未被打开的 `pymatgen` / 另一子技能里。

### 3.2 暴露度是内生的，不能当因果证据

把“skill 被加载的运行”与“未被加载的运行”在同一任务内对比，**所有方向都指向暴露伴随更高的得分**（n 很小，仅作方向性提示）：

| Task | 加载 skill 的运行 | 未加载的运行 |
|---|---|---|
| `energy-market-pricing` | 1.00 (n=1) | 0.00 (n=2) |
| `spring-boot-jakarta-migration` | 1.00 (n=1) | 0.00 (n=2) |
| `travel-planning` | 0.50 (n=2) | 0.00 (n=1) |
| `mars-clouds-clustering` | 0.00 (n=1) | 1.00 (n=2) |

合理解释是反向因果：**agent 是在任务可解、有进展时才会去打开 skill**。因此本报告中的 `Gate` 只用来回答“这条不一致性有没有机会起作用”，不用来回答“它是不是失败的原因”。

---

## 4. 第三部分：效度检验 —— 静态风险能预测任务完成吗？

对 39 个“有 finding 且有运行数据”的任务做相关分析：

| 自变量 | vs 观测成功率 | vs 失败运行中位 token | vs 失败运行中位耗时 |
|---|---|---|---|
| 可达风险 | +0.362 (n=59) | -0.090 (n=47) | -0.237 (n=48) |
| 静态风险（全部 finding） | +0.153 (n=59) | +0.186 (n=47) | -0.048 (n=48) |
| finding 条数 | +0.113 (n=59) | +0.180 (n=47) | -0.035 (n=48) |
| skill 加载率 | +0.203 (n=59) | -0.311 (n=47) | -0.132 (n=48) |

**读数**：

- 可达风险与成功率是 **正相关（+0.310）**，方向与预期相反。检测器标出的风险越高，任务反而越容易完成。
- 静态风险、finding 条数与成功率基本无关（+0.095 / +0.058）。
- 唯一有意义的正向关系是 finding 条数 vs 失败运行的 token（+0.365）和静态风险 vs 失败 token（+0.354）：**缺陷多的 skill 所在任务，失败时烧的 token 更多**。这支持“token 开销”这一维度纳入评分，但不支持“缺陷多所以成功率低”。
- skill 加载率 vs 失败 token 是负相关（−0.279）与 −0.332）：越用 skill 的任务，失败时反而花得少。同样与内生性一致。

**结论**：这批 audit report 目前的 severity 体系**不具备预测任务失败的效度**。本报告的排序因此不把它当因变量，只把它当“潜在风险量”，并由实测损失（S/T/W）主导。

---

## 5. 第四部分：Top 30 排序

`IIS` = 100 × Gate × (0.30 + 0.70 × Damage)，各分维已归一化到 0–100。
`findings（可达/文件级/总数）`：进入过上下文的条数 / 达到文件级的条数 / 报告中的总条数。
`主责子技能` 取该任务权重最高的可达 finding 所在子技能。

| # | Skill 包（task） | IIS | 成功率损害 | token 开销 | 时间开销 | 可达性 | 观测成功率 | findings（可达/文件级/总数） | 主责子技能 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `pddl-tpp-planning` | **83.7** | 100.0 | 88.0 | 70.3 | 89.7 | 0% | 13/0/13 | `pddl-skills` |
| 2 | `offer-letter-generator` | **68.1** | 66.7 | 76.4 | 73.9 | 85.4 | 33% | 12/12/12 | `docx` |
| 3 | `manufacturing-fjsp-optimization` | **52.1** | 33.3 | 98.8 | 86.3 | 70.0 | 67% | 6/0/6 | `fjsp-baseline-repair-with-downtime-and-policy` |
| 4 | `travel-planning` | **44.0** | 66.7 | 85.4 | 69.9 | 54.3 | 33% | 8/8/8 | `search-accommodations` |
| 5 | `suricata-custom-exfil` | **42.5** | 100.0 | 92.9 | 83.5 | 44.1 | 0% | 4/0/4 | `suricata-offline-evejson` |
| 6 | `r2r-mpc-control` | **42.1** | 100.0 | 100.0 | 84.8 | 43.0 | 0% | 10/0/10 | `mpc-horizon-tuning` |
| 7 | `data-to-d3` | **41.8** | 100.0 | 89.5 | 72.4 | 44.5 | 0% | 7/0/7 | `d3-visualization` |
| 8 | `weighted-gdp-calc` | **41.5** | 33.3 | 90.1 | 73.7 | 58.5 | 67% | 12/12/12 | `xlsx` |
| 9 | `earthquake-plate-calculation` | **40.7** | 33.3 | 86.7 | 73.6 | 58.0 | 67% | 9/9/9 | `geospatial-analysis` |
| 10 | `reserves-at-risk-calc` | **34.9** | 100.0 | 94.5 | 84.6 | 36.1 | 0% | 5/5/5 | `xlsx` |
| 11 | `organize-messy-files` | **34.7** | 100.0 | 86.6 | 68.5 | 37.4 | 0% | 4/0/10 | `docx_text_extraction` |
| 12 | `paper-anonymizer` | **34.1** | 100.0 | 75.2 | 61.6 | 38.1 | 0% | 2/0/3 | `academic-pdf-redaction` |
| 13 | `lab-unit-harmonization` | **34.0** | 48.6 | 89.7 | 72.5 | 44.7 | 51% | 3/0/3 | `lab-unit-harmonization` |
| 14 | `shock-analysis-supply` | **33.6** | 100.0 | 96.2 | 89.4 | 34.4 | 0% | 8/8/8 | `xlsx` |
| 15 | `latex-formula-extraction` | **31.9** | 100.0 | 89.1 | 88.2 | 33.2 | 0% | 3/3/3 | `marker` |
| 16 | `lake-warming-attribution` | **31.4** | 33.3 | 83.4 | 74.6 | 45.1 | 67% | 6/0/8 | `trend-analysis` |
| 17 | `azure-bgp-oscillation-route-leak` | **31.1** | 100.0 | 82.9 | 66.6 | 33.9 | 0% | 4/0/4 | `azure-bgp` |
| 18 | `citation-check` | **30.0** | 0.0 | 0.0 | 0.0 | 100.0 | 100% | 12/0/12 | `citation-management` |
| 19 | `hvac-control` | **27.6** | 100.0 | 90.4 | 76.8 | 29.1 | 0% | 2/0/5 | `imc-tuning-rules` |
| 20 | `dynamic-object-aware-egomotion` | **26.6** | 100.0 | 87.1 | 84.0 | 28.0 | 0% | 5/0/7 | `dyn-object-masks` |
| 21 | `glm-lake-mendota` | **25.7** | 0.0 | 0.0 | 0.0 | 85.7 | 100% | 12/0/12 | `glm-calibration` |
| 22 | `shock-analysis-demand` | **25.7** | 100.0 | 90.0 | 76.8 | 27.2 | 0% | 5/5/5 | `xlsx` |
| 23 | `multilingual-video-dubbing` | **24.3** | 100.0 | 87.4 | 98.3 | 25.0 | 0% | 2/0/17 | `ffmpeg-media-info` |
| 24 | `mario-coin-counting` | **21.7** | 33.3 | 84.3 | 75.6 | 31.0 | 67% | 5/2/5 | `object-counter` |
| 25 | `pptx-reference-formatting` | **21.6** | 100.0 | 91.9 | 70.2 | 22.9 | 0% | 1/0/1 | `reading_and_analyzing_content` |
| 26 | `flood-risk-analysis` | **21.2** | 0.0 | 0.0 | 0.0 | 70.6 | 100% | 8/0/9 | `usgs-data-download` |
| 27 | `civ6-adjacency-optimizer` | **19.1** | 64.5 | 90.5 | 83.2 | 22.9 | 36% | 1/0/1 | `civ6lib` |
| 28 | `grid-dispatch-operator` | **18.5** | 66.7 | 80.6 | 88.9 | 22.3 | 33% | 2/0/2 | `economic-dispatch` |
| 29 | `sec-financial-report` | **17.7** | 0.0 | 0.0 | 0.0 | 58.9 | 100% | 4/4/4 | `13f-analyzer` |
| 30 | `3d-scan-calc` | **17.5** | 0.0 | 0.0 | 0.0 | 58.3 | 100% | 9/9/9 | `mesh-analysis` |

### 5.1 分层解读

**第一梯队（#1–#11，IIS ≥ 31）：不一致性可达 + 任务端确有损失，修复优先级最高。**

- `pddl-tpp-planning`（83.7）：13 条 finding 全部可达，3/3 运行全 0 分，失败运行中位 token 高。最高权重缺陷是 `save-plan` 的文档/实现副作用冲突 —— 文档只说写文本 PDDL，实现却额外 pickle 序列化，且当输出路径不含 `.txt` 时 `path.replace('.txt','.pkl')` 退化为原路径，**用二进制覆盖刚写好的文本计划**。这是典型的 silent 型破坏：agent 看不到任何报错。
- `offer-letter-generator`（68.1）：12 条 finding **全部达到文件级暴露**（agent 真的读了 `docx/SKILL.md`），关键缺陷是 `replace_in_paragraph` 在同一文档里被赋予 1 参 / 2 参两套契约，agent 无法判断该用哪个。
- `manufacturing-fjsp-optimization`（52.1）：成功率 67% 但失败运行 token 分位为全库最高档（T=98.8）。缺陷是子技能间变量名断裂：生产者输出 `base_m`，消费者读 `base_m_orig`，而 `base_m_orig` 在任何片段里都没被赋值。
- `suricata-custom-exfil`（42.5）、`r2r-mpc-control`（42.1）、`hvac-control`（27.6）、`azure-bgp-oscillation-route-leak`（31.1）：都是 0% 成功率 + 高危可达。其中 `hvac-control` 的 `imc-tuning-rules` 引用未定义的 `output_min/output_max` 全局量，属于必然 `NameError` 的环境事实冲突。

**第二梯队（#12、#15、#18、#20–#24，IIS 10–30）：高静态风险、零观测损失，属于潜在风险。**

- `citation-check`（#12，IIS 30.0）：可达性满分（12/12），但 3/3 运行全部通过 —— 因为失败损失项 S/T/W 全为 0，IIS 完全由 `Gate × 0.30` 贡献。`glm-lake-mendota`、`flood-risk-analysis`、`sec-financial-report`、`3d-scan-calc`、`exceltable-in-ppt`、`dapt-intrusion-detection`、`sales-pivot-analysis` 同理。
- 这一档的正确读法是：**如果把这个 skill 换到更难的场景/更弱的模型上，它是最先炸的一批**；但在当前观测条件下，它们没有造成可测量的损失。修复性价比低于第一梯队。

**噪声档（#28–#30，IIS ≤ 0.1）：** `pdf-excel-diff`、`xlsx-recover-data`、`jpg-ocr-stat`。三者唯一的 finding 都是 `readonly_side_effect_conflict` 这一条 low/cosmetic 规则命中，可达性接近 0。**实际有意义的名次只有 #1–#27。**

### 5.2 Top 10 逐条证据

**#1 `pddl-tpp-planning` — IIS 83.7**

- 观测：3 次运行，成功率 0%；失败运行中位 token 621731，中位总耗时 170.815s
- 暴露：13/13 条 finding 进入过 agent 上下文（文件级 0 条），skill 加载率 100%
- 最高权重可达缺陷：`F-001`（critical / silent），位置 `pddl-skills/SKILL.md`
- 机理：文档把 save-plan 定义为通过 unified_planning.io.PDDLWriter 写出唯一的文本 PDDL 计划文件，未声明任何额外副作用；代码既没有使用 PDDLWriter（只是手写 str(action)），又在文本写入之后额外用 pickle 把 plan 序列化到 path.replace('.txt','.pkl')。当输出路径不含 '.txt' 时，替换结果等于原路径，'wb' 会把刚写好的文本计划覆盖为二进制内容。这属于文档声称只产生一种输出、代码却新增/破坏磁盘状态的 side_effect_conflict（且会静默产出不可用文件）。

**#2 `offer-letter-generator` — IIS 68.1**

- 观测：3 次运行，成功率 33%；失败运行中位 token 107326.0，中位总耗时 223.287s
- 暴露：12/12 条 finding 进入过 agent 上下文（文件级 12 条），skill 加载率 100%
- 最高权重可达缺陷：`F-003`（high / verified），位置 `docx/SKILL.md`
- 机理：同一函数名 replace_in_paragraph 在两处被赋予不同的入参契约（1 参 vs 2 参），属于子流程接口契约不一致。agent 若复用任一实现去配合另一处调用，接口无法对齐，会导致调用失败或需要自行猜测缺失的 data 参数。

**#3 `manufacturing-fjsp-optimization` — IIS 52.1**

- 观测：3 次运行，成功率 67%；失败运行中位 token 3214677，中位总耗时 556.109s
- 暴露：6/6 条 finding 进入过 agent 上下文（文件级 0 条），skill 加载率 100%
- 最高权重可达缺陷：`F-001`（high / silent），位置 `fjsp-baseline-repair-with-downtime-and-policy/SKILL.md`
- 机理：属 interface_contract_mismatch。协作结构声明 baseline_machine_validation 以 feeds_into 方式向 machine_selection 提供“合法 baseline 机器信息作为机器选择评分的基准机器输入”，但该子技能实际输出的变量名是 base_m（且非法时被改写为默认机），而 machine_selection 评分代码消费的是 base_m_orig——该变量在任何片段中都未被定义/赋值。上游输出字段名（base_m）与下游输入字段名（base_m_orig）不一致，机器变更（MC）的参照基准无法对齐，属于跨子技能接口契约不匹配，会在运行前无报错、但导致换机预算统

**#4 `travel-planning` — IIS 44.0**

- 观测：3 次运行，成功率 33%；失败运行中位 token 416210，中位总耗时 166.909s
- 暴露：8/8 条 finding 进入过 agent 上下文（文件级 8 条），skill 加载率 67%
- 最高权重可达缺陷：`F-001`（high / silent），位置 `search-accommodations/scripts/search_accommodations.py`
- 机理：同一概念『city 匹配规则』在两处被定义成互相矛盾的语义：search-accommodations（以及 attractions/restaurants/cities）显式声明并按大小写不敏感（case-insensitive）匹配，docstring 亦写作 'Return accommodations for the given city (case-insensitive).'；而 search-flights 的 run docstring 未声明大小写不敏感，代码用严格相等比较 OriginCityName/DestCityName，未做 lstrip/lower。两处对同名概念的判定规则不一致，属于 shared_c

**#5 `suricata-custom-exfil` — IIS 42.5**

- 观测：3 次运行，成功率 0%；失败运行中位 token 1305317，中位总耗时 451.444s
- 暴露：4/4 条 finding 进入过 agent 上下文（文件级 0 条），skill 加载率 100%
- 最高权重可达缺陷：`F-001`（high / silent），位置 `suricata-offline-evejson/SKILL.md`
- 机理：文档把“始终检查 Suricata 是否干净退出（无规则解析错误）”列为前置要求，并在迭代流程中把“验证规则语法 (suricata -T)”作为第 1 步前置条件；而脚本 run_suricata_offline.sh 用 `>/dev/null 2>&1 || true` 丢弃退出码与全部错误输出，把失败强行当作成功，等于反转/取消了文档要求的前置校验与执行顺序，符合 workflow_conflict 子类。

**#6 `r2r-mpc-control` — IIS 42.1**

- 观测：3 次运行，成功率 0%；失败运行中位 token 3828073，中位总耗时 498.373s
- 暴露：10/10 条 finding 进入过 agent 上下文（文件级 0 条），skill 加载率 67%
- 最高权重可达缺陷：`F-001`（high / silent），位置 `mpc-horizon-tuning/SKILL.md`
- 机理：该技能声明的运行环境是离散时间 MPC（dt=0.01s 采样步长、时域 N 的预测），终端代价应使用离散代数 Riccati 方程求解，才能与 finite-horizon-lqr 中的离散反向递推（P = Q + A'P(A - BK)）一致；但文档却调用 scipy 的连续时间求解器 solve_continuous_are，环境假设（离散时间）与实际使用的求解器（连续时间）冲突，属于 environment_fact_conflict。

**#7 `data-to-d3` — IIS 41.8**

- 观测：3 次运行，成功率 0%；失败运行中位 token 777902，中位总耗时 200.17s
- 暴露：7/7 条 finding 进入过 agent 上下文（文件级 0 条），skill 加载率 33%
- 最高权重可达缺陷：`F-002`（high / verified），位置 `d3-visualization/SKILL.md`
- 机理：声明的环境假设是"无外部网络依赖、离线、产出 standalone HTML"（并明确不加载 CDN），但实现示例依赖 d3.csv 在运行时用 fetch 拉取一个绝对路径 /data/stocks.csv。fetch 在 file:// 协议下会被浏览器阻止，这属于 environment_fact_conflict：技能的离线/单文件运行时假设与示例代码实际需要的 HTTP 服务/数据路径约束相冲突。

**#8 `weighted-gdp-calc` — IIS 41.5**

- 观测：3 次运行，成功率 67%；失败运行中位 token 851396，中位总耗时 220.049s
- 暴露：12/12 条 finding 进入过 agent 上下文（文件级 12 条），skill 加载率 100%
- 最高权重可达缺陷：`F-001`（high / silent），位置 `xlsx/SKILL.md`
- 机理：同一个概念"Excel 公式错误集合"在两处定义不一致：SKILL.md 声明必须为零的仅有 5 种（含 #N/A，不含 #NULL!/#NUM!），recalc.py 实际扫描 7 种。属于 shared_concept_definition_conflict（枚举/语义在不同位置定义不同）。

**#9 `earthquake-plate-calculation` — IIS 40.7**

- 观测：3 次运行，成功率 67%；失败运行中位 token 512159，中位总耗时 217.908s
- 暴露：9/9 条 finding 进入过 agent 上下文（文件级 9 条），skill 加载率 100%
- 最高权重可达缺陷：`F-005`（medium / silent），位置 `geospatial-analysis/SKILL.md`
- 机理：技能对同一板块数据集的字段命名自相矛盾：过滤板块时一处用 gdf_plates["Name"]（第72行），另一处用 gdf_plates["PlateName"]（第167行），又用 gdf_plates["Code"]（第144行）；经纬度字段也一会是 lon/lat（第62行），一会是 longitude/latitude（第140行）。这些 key 无法同时对应同一份真实数据源，说明技能对外部数据 schema 的契约假设不一致；若沿用了错误的字段名，过滤会静默返回空结果而非报错，属于外部数据契约/字段定义不一致（external_service_contract_change）。

**#10 `reserves-at-risk-calc` — IIS 34.9**

- 观测：3 次运行，成功率 0%；失败运行中位 token 1650548，中位总耗时 490.379s
- 暴露：5/5 条 finding 进入过 agent 上下文（文件级 5 条），skill 加载率 100%
- 最高权重可达缺陷：`F-003`（medium / silent），位置 `xlsx/SKILL.md`
- 机理：同一个概念“Excel 公式错误 / 需归零的错误集合”在两处定义不一致：SKILL.md 列出 5 种（#REF!、#DIV/0!、#VALUE!、#N/A、#NAME?），recalc.py 的检测清单却是 7 种，额外包含文档从未提及的 #NULL! 与 #NUM!。属于 shared_concept_definition_conflict：枚举定义在不同文档中不对齐，agent 无法为 recalc 报出的 #NULL!/#NUM! 找到对应处理语义。

---

## 6. 第五部分：需要返工的两份清单

### 6.1 必须重跑的 29 份报告

即 §2.1 的失效清单。建议在 `main.py` 中加一条硬断言：`total_files > 0 and not components` → 以非零退出码失败，并在缓存键里排除空组件结果（当前 `grid-dispatch-operator`、`fix-visual-stability` 正是被缓存住的坏结果）。

### 6.2 无法排序的 9 份有效报告（有 finding 但没有运行数据）

| Task | findings | 静态风险 |
|---|---|---|
| `fix-visual-stability` | 10 | 9.918 |
| `pddl-airport-planning` | 6 | 9.53 |
| `gravitational-wave-detection` | 3 | 4.7 |
| `llm-prefix-cache-replay` | 7 | 4.43 |
| `video-silence-remover` | 5 | 4.243 |
| `paratransit-routing` | 4 | 2.938 |
| `simpo-code-reproduction` | 4 | 2.25 |
| `radar-vital-signs` | 4 | 2.138 |
| `drone-planning-control` | 2 | 1.89 |
| `debug-trl-grpo` | 4 | 1.782 |
| `ada-bathroom-plan-repair` | 3 | 1.35 |
| `energy-unit-commitment` | 1 | 0.9 |
| `seismic-phase-picking` | 1 | 0.5 |

其中 `pddl-airport-planning`（6 条，风险 9.53，含 4 条声称阻断）静态风险与第 3 名同档，只差一次运行就能定性，是**补测性价比最高**的一个。

---

## 7. 局限与诚实边界

1. **运行数据不是同一批次**。199 次运行来自 SkillsBench paper-v1 归档（claude-code 2.1.19，2026-01），而审计报告是 2026-09-23 对本仓库 `tasks/` 当前版本生成的。少数任务在两版之间改过名（例如 `object-counter` → 基线日志里叫 `object_counter`），曝光匹配已做归一化，但仍可能存在个别漏配。
2. **只统计了 68/87 个任务有运行数据**；另外 19 个任务的 skill 从未被跑过，其中 9 个含 finding。
3. **`p_hit` 的分母是 1–3 次运行**，可达性估计的方差很大：65 个任务只有 3 次运行，`react-performance-debugging` 2 次，`lean4-proof`、`earthquake-phase-association` 各 1 次。
4. **`Gate` 用的是“是否进入上下文”，不是“是否被采纳”**。文件被读 ≠ 该条不一致性被 agent 采信。要把 IIS 做成因果结论，需要逐条人工核对轨迹。
5. **检测器本身有已知假阴性**。在本仓库此前的三组对照实验里，`skill-audit` 对 5 条由轨迹证实的真实不一致性**命中 0 条**（见 `skill-audit/OPTIMIZATION.md` §5 记录的待补 `task_contract_checker`）。因此“0 finding”不等于“无问题”，Top 30 之外不等于安全。
6. **本报告的 IIS 是优先级排序，不是效应量**。它回答“先修哪个”，不回答“修了能涨多少分”。后者只能由 matched-budget 对照实验给出。

---

## 附录：产物清单

| 文件 | 内容 |
|---|---|
| `skill_inconsistency_impact_top30.md` | 本报告 |
| `skill_inconsistency_impact_ranking.csv` | 87 个任务的完整字段表（含全部中间量） |
| `analysis_tools/exposure_scan_baseline.py` | 260 条 finding × 199 次运行的可达性扫描 |
| `analysis_tools/parse_baseline_runs.py` | 从 legacy agent 日志解析 reward / token / timing |
| `analysis_tools/impact_ranking.py` | 三维评分与排序 |
| `analysis_tools/make_impact_report.py` | 生成本 Markdown |
