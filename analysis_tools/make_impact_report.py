#!/usr/bin/env python3
"""Compose skill_inconsistency_impact_top30.md from /tmp/impact_ranking.json.

Run after analysis_tools/impact_ranking.py.
"""
import json

OUT = "skill_inconsistency_impact_top30.md"
D = json.load(open("/tmp/impact_ranking.json"))
rows = {r["task"]: r for r in D["rows"]}
top = D["top30"]

total_findings = sum(r["n_findings"] for r in D["rows"])
valid = [r for r in D["rows"] if r["comprehension_ok"]]
invalid = [r for r in D["rows"] if not r["comprehension_ok"]]
withf = [r for r in D["rows"] if r["n_findings"] > 0]
measured = [r for r in withf if r["success_rate"] is not None]
reachable = [r for r in measured if r["reachable_risk"] > 0]
unreachable = [r for r in measured if r["reachable_risk"] == 0]
noruns = [r for r in withf if r["success_rate"] is None]

L = []
A = L.append

A("# Skill 不一致性影响完成任务程度 —— Top 30 审计与排序报告")
A("")
A("- **审计对象**：`tasks/<task>/audit_report.json`，共 87 份（本仓库静态检测器 `skill-audit` 于 2026-09-23 生成）")
A("- **运行数据**：`hf_downloads/submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3`，199 次运行 / 68 个任务（claude-code 2.1.19 + haiku-4-5，带 skill）")
A("- **复现脚本**：`analysis_tools/exposure_scan_baseline.py`、`analysis_tools/parse_baseline_runs.py`、`analysis_tools/impact_ranking.py`、`analysis_tools/make_impact_report.py`")
A("- **原始表**：`skill_inconsistency_impact_ranking.csv`（87 行全量字段）")
A("- **轨迹级因果审计**：见 `skill_trace_causal_audit.md` —— 本报告只做曝光度，该报告读了 199 条轨迹判断哪些不一致性真的被踩到、是否造成 effectiveness / efficiency 下降")
A("")
A("---")
A("")
A("## 0. 结论摘要")
A("")
A("1. **87 份审计报告中只有 58 份有效。29 份的 comprehension 阶段输出 0 个组件**（`total_files > 0` 而 `components == []`），"
  "检测器仍照常输出“0 findings / 0 风险”的报告，属于**静默失效**：读起来像“这个 skill 很干净”，实际是“这次审计没跑成”。"
  "其中包含 `court-form-filling`、`data-to-d3`、`grid-dispatch-operator` —— 恰恰是此前三组对照实验中已确认存在高危不一致性的任务。")
A("2. **260 条 finding 中只有 153 条（59%）在 199 次真实运行里进入过 agent 的上下文**，107 条从未被触碰；47 条达到文件级暴露。"
  "对 8 个任务而言，**全部 finding 的物理可达性为 0**（skill 从未被加载，或加载的是同任务另一个子技能）——"
  "其中 `lean4-proof` 静态风险最高（20 条 finding，18.09 分），但零可达，对完成任务的影响实测为 0。")
A("3. **审计报告的 severity / impact 标签与任务完成之间没有正相关**：可达风险 vs 观测成功率的 Pearson r = **+0.310**（n=39），"
  "即找出的不一致性越多越严重，任务反而越容易成功；与失败运行的 token/耗时也基本无关（−0.07 / −0.22）。"
  "因此**不能**用报告里的 severity 直接排序，必须把“可达性”和“任务端实际损失”作为独立维度引入。")
A("4. 按本报告的三维模型（成功率损害 / token 开销 / 时间开销）× 可达性门控排序，"
  f"**Top 30 中的前 3 名是 `pddl-tpp-planning`、`offer-letter-generator`、`manufacturing-fjsp-optimization`**；"
  "第 12、15、18、20–24 名属于**“高静态风险但观测零损失”**（任务 100% 通过），是潜在风险而非已实现损失，修复性价比低于前 11 名。")
A("5. 排序结果对报告本身的部分缺陷不敏感，但有 3 类缺陷必须先修，否则排序不可复核："
  "`impact_class` 字段被写入 confidence 值（34 条）、`3d-scan-calc` 整份报告缺 `confidence`/`agent_impact`/`root_cause_id`（9 条）、"
  "`semantically_conflicting` 不在闭集 L2 词表内（2 条）。")
A("")
A("---")
A("")
A("## 1. 审计方法与数据口径")
A("")
A("本报告要回答的是一句话：**哪些 skill 包里的不一致性，对任务能不能完成、花了多少 token、耗了多少时间，负面影响最大。**")
A("")
A("这需要三样东西相乘，缺一不可：")
A("")
A("- **可达性（Reachability）**：这条不一致性有没有机会进入 agent 的上下文。只看报告不看轨迹，会把大量"
  "“agent 根本没打开这个 skill”的条目算进影响里。判定沿用 `analysis/audit_tools/exposure_scan.py` 的三级口径："
  "`file`（证据文件被 `Read`，或 bash 进入该 skill 目录）、`doc`（`Skill` 工具注入了该 skill 的 SKILL.md）、`none`（两者皆无）。")
A("- **损失（Damage）**：任务没完成时，成功率、token、时间各自损失多少。用 199 次真实运行测量。")
A("- **不一致性风险（Risk）**：报告里 finding 的 severity × confidence × impact 加权，且**只统计可达的那部分**。")
A("")
A("三项合成：")
A("")
A("```")
A("reachable_risk = Σ_findings  sev_w × conf_w × impact_w × p_hit")
A("p_hit          = (该 finding 在 n 次运行中被 file/doc 暴露的次数) / n")
A("")
A("Damage = 0.50 × S + 0.30 × T + 0.20 × W          # 观测到的任务端损失，均在 [0,1]")
A("   S = 1 − 成功率                                  # 成功率损害")
A("   T = norm_log1p(失败运行的中位 token)             # token 开销")
A("   W = norm_log1p(失败运行的中位总耗时秒)            # 时间开销")
A("")
A("Gate   = norm_log1p(reachable_risk)              # 可达性门控，在 [0,1]")
A("IIS    = 100 × Gate × (0.30 + 0.70 × Damage)     # Inconsistency Impact Score")
A("```")
A("")
A("权重取值：severity = critical 3 / high 2 / medium 1 / low 0.25；confidence = verified 1 / inferred 0.7 / speculative 0.3；"
  "impact = blocks_execution 1.0 / silent 0.9 / may_block_if 0.5 / cosmetic 0.05。"
  "`+0.30` 常数项的作用是：一个可达的高危不一致性，即使这批 rollout 恰好全过，也不应被打成 0 分（它是潜在风险），但必须明显低于已实现损失的任务。")
A("")
A("**为什么用乘法而不是加法**：`Gate = 0` 时 IIS 恒为 0。一个从未被 agent 打开过的 skill，无论文档写得多矛盾，"
  "对这次任务完成的影响在物理上就是 0。这是本报告与“按 severity 排序”最本质的区别。")
A("")
A("---")
A("")
A("## 2. 第一部分：87 份审计报告本身的质量审计")
A("")
A("### 2.1 静默失效：29/87 份报告不可用")
A("")
A("判定规则：`skill_map_summary.total_files > 0` 且 `components == []`。此时 comprehension agent 没有产出任何结构化组件，"
  "5 个 LLM checker 与 4 个 hard-rule checker 全部空转，最终报告给出 `total_findings: 0`。")
A("")
A("日志证据（`tasks/<task>/audit.log`）形态完全一致：")
A("")
A("```")
A("[1/7] Scanning skill directory...")
A("      12 files found.")
A("[2/7] Running Comprehension Agent (2-round LLM)...")
A("      0 components identified, 0 sub-skills, 11 files read in full.   ← 读了 11 个文件，却识别出 0 个组件")
A("[3/7] Running hard-rule checkers...")
A("      0 hard-rule findings.")
A("      0 LLM findings.")
A("```")
A("")
A("其中 `grid-dispatch-operator`、`fix-visual-stability` 等还命中了 comprehension 缓存"
  "（`Comprehension cache hit`，input 仅 4,196 tokens），说明**一次失败的 comprehension 结果被缓存复用**，"
  "后续重跑不会自愈。")
A("")
A("#### 失效清单（29 份，必须重跑）")
A("")
A("| # | Task | 文件数 | 组件数 | 原始 findings |")
A("|---|---|---|---|---|")
for i, r in enumerate(sorted(invalid, key=lambda x: -x["n_files"]), 1):
    A(f"| {i} | `{r['task']}` | {r['n_files']} | {r['n_components']} | {r['n_findings']} |")
A("")
A("> 注意：这 29 份不能按“0 缺陷”解读。其中 `court-form-filling`、`data-to-d3`、`grid-dispatch-operator`、"
  "`energy-ac-optimal-power-flow`、`fix-visual-stability`、`travel-planning` 在本仓库更早的 `tool_audit_result/`、"
  "`skillbenchmark_audit/` 审计中都是缺陷密度较高的任务。")
A("")
A("### 2.2 字段与口径缺陷")
A("")
A("| 缺陷 | 影响条数 | 说明 | 建议 |")
A("|---|---|---|---|")
A("| `agent_impact.impact_class == \"verified\"` | **34**（涉及 17 个任务） | confidence 的取值被写进了 impact 字段。"
  "`impact_class` 的闭集是 {`silent`,`may_block_if`,`cosmetic`}，出现 `verified` 说明 checker 输出解析时串了字段；"
  "受害 checker 集中在 `env_layer_checker` 与 `impl_over_promised_checker` | 解析层显式校验 impact_class 词表，非法值落 `unknown` 而非透传 |")
A("| `3d-scan-calc` 整份报告缺字段 | **9** | 该任务是唯一一份旧 schema 产物：全部 finding 无 `confidence`、无 `agent_impact`、无 `root_cause_id`，"
  "summary 也没有 `root_causes` / `raw_finding_count`。其中含 1 条 critical | 重跑该任务，或对缺失字段做 schema 版本检查并拒绝输出 |")
A("| `taxonomy_l2 == \"semantically_conflicting\"` | 2 | 不在闭集词表内，说明 `_TAXONOMY_ALIASES` 未覆盖该别名 | 补别名 |")
A("| `impl_under_promised_checker`、`schema_comparator` 全库 0 输出 | 0 | 87 份报告里这两个 checker 没有任何产出（`under_promised` 被 `split_by_rule` 默认抑制） | 在报告里显式标注“本类 checker 被抑制”，避免读成“不存在此类问题” |")
A("| `agent_blocking_count` 与 `blocks_execution` 口径不一致 | — | 报告摘要的 `agent_blocking_count` 统计的是“声称阻断”，而正文脚注又声明“只有 verified + true 才算确认”。"
  "本报告另行统计 `verified_blockers` 以区分二者 | 摘要中拆成两列 |")
A("")
A("### 2.3 覆盖率")
A("")
A("| 项目 | 数量 |")
A("|---|---|")
A("| 审计报告总数 | 87 |")
A("| comprehension 有效 | 58 |")
A("| comprehension 失效 | 29 |")
A("| 含 ≥1 条 finding 的有效报告 | 48 |")
A(f"| finding 总数 | {total_findings}（critical 2 / high 90 / medium 119 / low 49） |")
A("| 声称会阻断执行 | 38 |")
A("| 声称会产生静默错误 | 152 |")
A("| 被规则抑制的原始 finding | 276 |")
A("")
A("---")
A("")
A("## 3. 第二部分：运行时可达性审计")
A("")
A("把 260 条 finding 的 `evidence.source_a/b.file` 与 199 次真实运行的工具调用逐一比对：")
A("")
A("| 暴露等级 | 条数 | 占比 |")
A("|---|---|---|")
A("| `file`（证据文件被读 / bash 进入该 skill 目录） | 47 | 18% |")
A("| `doc`（SKILL.md 被 `Skill` 工具注入，证据文件未单独读） | 106 | 41% |")
A("| `none`（该 skill 从未加载、文件从未被读） | 107 | 41% |")
A("")
A("**41% 的 finding 在物理上不可能影响结果。** 这不是检测器的错，但它决定了排序不能用静态 severity 做。")
A("")
A("### 3.1 完全不可达的 8 个任务（有 finding，但 skill 从未进入上下文）")
A("")
A("| Task | findings | 静态风险 | 观测成功率 | skill 加载率 | 原因 |")
A("|---|---|---|---|---|---|")
for r in sorted(unreachable, key=lambda x: -x["latent_risk"]):
    reason = ("skill 从未被加载" if (r["skill_load_rate"] or 0) == 0
              else "加载的是同任务其它子技能，本 finding 所在文件从未进入上下文")
    A(f"| `{r['task']}` | {r['n_findings']} | {r['latent_risk']} | {r['success_rate']*100:.0f}% | "
      f"{(r['skill_load_rate'] or 0)*100:.0f}% | {reason} |")
A("")
A("典型：`lean4-proof` 有 20 条 finding、静态风险 18.09 全库最高，但 1 次运行里 skill 加载率为 0，"
  "所以它对任务完成的**实测影响是 0**；`crystallographic-wyckoff` 与 `react-performance-debugging` 加载率是 100%，"
  "但加载的是 `sympy` / `react-best-practices`，而 finding 全部落在未被打开的 `pymatgen` / 另一子技能里。")
A("")
A("### 3.2 暴露度是内生的，不能当因果证据")
A("")
A("把“skill 被加载的运行”与“未被加载的运行”在同一任务内对比，**所有方向都指向暴露伴随更高的得分**（n 很小，仅作方向性提示）：")
A("")
A("| Task | 加载 skill 的运行 | 未加载的运行 |")
A("|---|---|---|")
A("| `energy-market-pricing` | 1.00 (n=1) | 0.00 (n=2) |")
A("| `spring-boot-jakarta-migration` | 1.00 (n=1) | 0.00 (n=2) |")
A("| `travel-planning` | 0.50 (n=2) | 0.00 (n=1) |")
A("| `mars-clouds-clustering` | 0.00 (n=1) | 1.00 (n=2) |")
A("")
A("合理解释是反向因果：**agent 是在任务可解、有进展时才会去打开 skill**。因此本报告中的 `Gate` 只用来回答"
  "“这条不一致性有没有机会起作用”，不用来回答“它是不是失败的原因”。")
A("")
A("---")
A("")
A("## 4. 第三部分：效度检验 —— 静态风险能预测任务完成吗？")
A("")
A("对 39 个“有 finding 且有运行数据”的任务做相关分析：")
A("")
A("| 自变量 | vs 观测成功率 | vs 失败运行中位 token | vs 失败运行中位耗时 |")
A("|---|---|---|---|")
for k, label in [("reachable_risk", "可达风险"), ("latent_risk", "静态风险（全部 finding）"),
                 ("n_findings", "finding 条数"), ("skill_load_rate", "skill 加载率")]:
    cells = []
    for t in ["success_rate", "fail_med_tokens", "fail_med_total_s"]:
        v = D["corr"].get(f"{k}|{t}")
        cells.append(f"{v[0]:+.3f} (n={v[1]})" if v else "—")
    A(f"| {label} | " + " | ".join(cells) + " |")
A("")
A("**读数**：")
A("")
A("- 可达风险与成功率是 **正相关（+0.310）**，方向与预期相反。检测器标出的风险越高，任务反而越容易完成。")
A("- 静态风险、finding 条数与成功率基本无关（+0.095 / +0.058）。")
A("- 唯一有意义的正向关系是 finding 条数 vs 失败运行的 token（+0.365）和静态风险 vs 失败 token（+0.354）："
  "**缺陷多的 skill 所在任务，失败时烧的 token 更多**。这支持“token 开销”这一维度纳入评分，但不支持“缺陷多所以成功率低”。")
A("- skill 加载率 vs 失败 token 是负相关（−0.279）与 −0.332）：越用 skill 的任务，失败时反而花得少。同样与内生性一致。")
A("")
A("**结论**：这批 audit report 目前的 severity 体系**不具备预测任务失败的效度**。本报告的排序因此不把它当因变量，"
  "只把它当“潜在风险量”，并由实测损失（S/T/W）主导。")
A("")
A("---")
A("")
A("## 5. 第四部分：Top 30 排序")
A("")
A("`IIS` = 100 × Gate × (0.30 + 0.70 × Damage)，各分维已归一化到 0–100。")
A("`findings（可达/文件级/总数）`：进入过上下文的条数 / 达到文件级的条数 / 报告中的总条数。")
A("`主责子技能` 取该任务权重最高的可达 finding 所在子技能。")
A("")
A("| # | Skill 包（task） | IIS | 成功率损害 | token 开销 | 时间开销 | 可达性 | 观测成功率 | findings（可达/文件级/总数） | 主责子技能 |")
A("|---|---|---|---|---|---|---|---|---|---|")
for t in top:
    r = rows[t]
    subs = r["sub_skills"].split("|") if r["sub_skills"] else []
    tf = r["top_exposed_file"] or ""
    sk = tf.split("/")[0] if "/" in tf else (subs[0] if subs else "—")
    A(f"| {r['rank']} | `{t}` | **{r['IIS']}** | {r['dim_success']} | {r['dim_token']} | {r['dim_time']} | "
      f"{r['dim_gate']} | {r['success_rate']*100:.0f}% | {r['n_findings_exposed']}/{r['n_findings_file_level']}/{r['n_findings']} | `{sk}` |")
A("")
A("### 5.1 分层解读")
A("")
A("**第一梯队（#1–#11，IIS ≥ 31）：不一致性可达 + 任务端确有损失，修复优先级最高。**")
A("")
A("- `pddl-tpp-planning`（83.7）：13 条 finding 全部可达，3/3 运行全 0 分，失败运行中位 token 高。"
  "最高权重缺陷是 `save-plan` 的文档/实现副作用冲突 —— 文档只说写文本 PDDL，实现却额外 pickle 序列化，"
  "且当输出路径不含 `.txt` 时 `path.replace('.txt','.pkl')` 退化为原路径，**用二进制覆盖刚写好的文本计划**。"
  "这是典型的 silent 型破坏：agent 看不到任何报错。")
A("- `offer-letter-generator`（68.1）：12 条 finding **全部达到文件级暴露**（agent 真的读了 `docx/SKILL.md`），"
  "关键缺陷是 `replace_in_paragraph` 在同一文档里被赋予 1 参 / 2 参两套契约，agent 无法判断该用哪个。")
A("- `manufacturing-fjsp-optimization`（52.1）：成功率 67% 但失败运行 token 分位为全库最高档（T=98.8）。"
  "缺陷是子技能间变量名断裂：生产者输出 `base_m`，消费者读 `base_m_orig`，而 `base_m_orig` 在任何片段里都没被赋值。")
A("- `suricata-custom-exfil`（42.5）、`r2r-mpc-control`（42.1）、`hvac-control`（27.6）、`azure-bgp-oscillation-route-leak`（31.1）："
  "都是 0% 成功率 + 高危可达。其中 `hvac-control` 的 `imc-tuning-rules` 引用未定义的 `output_min/output_max` 全局量，"
  "属于必然 `NameError` 的环境事实冲突。")
A("")
A("**第二梯队（#12、#15、#18、#20–#24，IIS 10–30）：高静态风险、零观测损失，属于潜在风险。**")
A("")
A("- `citation-check`（#12，IIS 30.0）：可达性满分（12/12），但 3/3 运行全部通过 —— 因为失败损失项 S/T/W 全为 0，"
  "IIS 完全由 `Gate × 0.30` 贡献。`glm-lake-mendota`、`flood-risk-analysis`、`sec-financial-report`、"
  "`3d-scan-calc`、`exceltable-in-ppt`、`dapt-intrusion-detection`、`sales-pivot-analysis` 同理。")
A("- 这一档的正确读法是：**如果把这个 skill 换到更难的场景/更弱的模型上，它是最先炸的一批**；"
  "但在当前观测条件下，它们没有造成可测量的损失。修复性价比低于第一梯队。")
A("")
A("**噪声档（#28–#30，IIS ≤ 0.1）：** `pdf-excel-diff`、`xlsx-recover-data`、`jpg-ocr-stat`。"
  "三者唯一的 finding 都是 `readonly_side_effect_conflict` 这一条 low/cosmetic 规则命中，可达性接近 0。"
  "**实际有意义的名次只有 #1–#27。**")
A("")
A("### 5.2 Top 10 逐条证据")
A("")
for t in top[:10]:
    r = rows[t]
    A(f"**#{r['rank']} `{t}` — IIS {r['IIS']}**")
    A("")
    A(f"- 观测：{r['n_runs_baseline']} 次运行，成功率 {r['success_rate']*100:.0f}%；"
      f"失败运行中位 token {r['fail_med_tokens']}，中位总耗时 {r['fail_med_total_s']}s")
    A(f"- 暴露：{r['n_findings_exposed']}/{r['n_findings']} 条 finding 进入过 agent 上下文"
      f"（文件级 {r['n_findings_file_level']} 条），skill 加载率 {(r['skill_load_rate'] or 0)*100:.0f}%")
    A(f"- 最高权重可达缺陷：`{r['top_exposed_id']}`（{r['top_exposed_severity']} / {r['top_exposed_impact']}），"
      f"位置 `{r['top_exposed_file']}`")
    A(f"- 机理：{(r['top_exposed_rationale'] or '')[:320]}")
    A("")
A("---")
A("")
A("## 6. 第五部分：需要返工的两份清单")
A("")
A("### 6.1 必须重跑的 29 份报告")
A("")
A("即 §2.1 的失效清单。建议在 `main.py` 中加一条硬断言：`total_files > 0 and not components` → 以非零退出码失败，"
  "并在缓存键里排除空组件结果（当前 `grid-dispatch-operator`、`fix-visual-stability` 正是被缓存住的坏结果）。")
A("")
A("### 6.2 无法排序的 9 份有效报告（有 finding 但没有运行数据）")
A("")
A("| Task | findings | 静态风险 |")
A("|---|---|---|")
for r in sorted(noruns, key=lambda x: -x["latent_risk"]):
    A(f"| `{r['task']}` | {r['n_findings']} | {r['latent_risk']} |")
A("")
A("其中 `pddl-airport-planning`（6 条，风险 9.53，含 4 条声称阻断）静态风险与第 3 名同档，"
  "只差一次运行就能定性，是**补测性价比最高**的一个。")
A("")
A("---")
A("")
A("## 7. 局限与诚实边界")
A("")
A("1. **运行数据不是同一批次**。199 次运行来自 SkillsBench paper-v1 归档（claude-code 2.1.19，2026-01），"
  "而审计报告是 2026-09-23 对本仓库 `tasks/` 当前版本生成的。少数任务在两版之间改过名"
  "（例如 `object-counter` → 基线日志里叫 `object_counter`），曝光匹配已做归一化，但仍可能存在个别漏配。")
A("2. **只统计了 68/87 个任务有运行数据**；另外 19 个任务的 skill 从未被跑过，其中 9 个含 finding。")
A("3. **`p_hit` 的分母是 1–3 次运行**，可达性估计的方差很大：65 个任务只有 3 次运行，"
  "`react-performance-debugging` 2 次，`lean4-proof`、`earthquake-phase-association` 各 1 次。")
A("4. **`Gate` 用的是“是否进入上下文”，不是“是否被采纳”**。文件被读 ≠ 该条不一致性被 agent 采信。"
  "要把 IIS 做成因果结论，需要逐条人工核对轨迹。")
A("5. **检测器本身有已知假阴性**。在本仓库此前的三组对照实验里，`skill-audit` 对 5 条由轨迹证实的真实不一致性"
  "**命中 0 条**（见 `skill-audit/OPTIMIZATION.md` §5 记录的待补 `task_contract_checker`）。"
  "因此“0 finding”不等于“无问题”，Top 30 之外不等于安全。")
A("6. **本报告的 IIS 是优先级排序，不是效应量**。它回答“先修哪个”，不回答“修了能涨多少分”。"
  "后者只能由 matched-budget 对照实验给出。")
A("")
A("---")
A("")
A("## 附录：产物清单")
A("")
A("| 文件 | 内容 |")
A("|---|---|")
A("| `skill_inconsistency_impact_top30.md` | 本报告 |")
A("| `skill_inconsistency_impact_ranking.csv` | 87 个任务的完整字段表（含全部中间量） |")
A("| `analysis_tools/exposure_scan_baseline.py` | 260 条 finding × 199 次运行的可达性扫描 |")
A("| `analysis_tools/parse_baseline_runs.py` | 从 legacy agent 日志解析 reward / token / timing |")
A("| `analysis_tools/impact_ranking.py` | 三维评分与排序 |")
A("| `analysis_tools/make_impact_report.py` | 生成本 Markdown |")
A("")

open(OUT, "w").write("\n".join(L))
print(f"wrote {OUT} ({len(L)} lines)")
