# RQ1 — Characterizing Skill Contract Inconsistencies · 数据与写作素材

> **v2（2026-09-28）**：并入 SkillBench findings 复核结果。SkillBench 全部数字改为**复核后**口径，
> 并保留审计原值作为对照；GitHub 语料**尚未复核**，一律标注为 “unverified / 上界”。
> 旧版（全部按审计原值）已备份为 `RQ1_RESULTS_v1_audited.md`。

本文件是 RQ1 的**结果底稿**：每个小节给出「要回答的问题 → 数据 → 图/表 → 可直接写进论文的英文陈述句」，
最后是 3 个 Finding box。所有数字由脚本从审计报告直接算出，改数据后重跑即可更新。

```bash
cd paper_audit_reports/rq1_analysis && bash run_all.sh        # 基础统计（审计原值）
cd ../skillbench_verification && python3 apply_verification.py # 复核后的 SkillBench 口径
```

---

## 0. 数据状态与口径（写 Methods / 脚注用）

### 0.1 复核状态 —— 写作前必读

我们对 **SkillBench 的全部 377 条 finding 做了逐条复核**（机械证据核对 + 独立语义复核 + 对抗裁定），
结论是 **只有 160 条（42.4%）符合我们定义的不一致性**：120 条确证、40 条确有其事但层级标错，
217 条（57.6%）不成立。因此本文档中 **SkillBench 一律用复核后的 160 条**（`mislabeled` 用修正后的标签）。

**GitHub 语料（488 skill / 1022 finding）尚未复核。** 两个语料共用同一套 checker，而 SkillBench 上
`env_constraint_checker` 存活 0/14、`url_validator` 0/7、`dependency_version_drift` 1/16，
所以 **GitHub 的数字应视为上界**，凡是跨语料对比都必须注明这一点。

| 口径 | 含义 | 用途 |
|---|---|---|
| `as audited` | 审计器原始输出 | 仅作对照 / 说明复核增益 |
| `verified` | SkillBench 仅保留 confirmed + mislabeled（用修正标签） | **SkillBench 的正式数字** |
| `unverified` | GitHub 原始输出（上界） | 需标注 caveat 后才能使用 |

### 0.2 两个语料

| 语料 | 来源 | Skill 数 | Finding 数（口径） |
|---|---|---|---|
| GitHub Skills | `wildskills_audit/`，公开 GitHub 仓库采样的社区 Skill | 488 | 1,022（**未经复核**） |
| SkillBench | `skillbench_audit/`，基准任务内置 Skill | 87 | 377 审计 → **160 复核后** |

**Finding 口径**：审计报告 `findings[]` 中通过硬规则与 LLM 校验后保留的条目
（`validation_status ∈ {confirmed, hard_rule}`），已剔除被 suppress 的假阳性。

**Contract claim（密度分母）**：文档声明（`.md` 中剥离 frontmatter/标题/代码块后的句子、列表项、表格行）
+ 代码接口声明（函数定义数 + 形参个数）；`Inconsistencies / 100 claims` = finding 数 ÷ claim 数 × 100。

**Artifact boundary（taxonomy L1）**：`Document–Code`（实现层）、`Document–Document`（文档层）、
`Skill–Environment`（环境层）。

**Contract element（facet）**：实现层用 L3，其余用 L2 映射到"契约的哪一部分"。

### 0.3 写作时的三条硬约束

1. **不要把 SkillBench 写成 82.8% / 377**，那是审计原值；正式数字是 **64.4% / 160**。
2. **不要声称跨语料的密度或负载差异**（例如"SkillBench 负载是 GitHub 的两倍"）——复核后该结论消失
   （见 Finding 3）。要么先复核 GitHub，要么只陈述"两者量级相近"。
3. **环境层的比例被严重高估**：SkillBench 上环境层从 33.2% 跌到 15.6%，因此"三个 boundary 相对均衡"
   这句话在 SkillBench 上不成立；GitHub 侧同样偏环境层，需复核后才能定论。

---

## A. Prevalence and Density

### A.1 How prevalent?

数据：`rq1_analysis/outputs/table1_prevalence.csv`、`skillbench_verification/outputs/verified/table1_prevalence_verified.csv`
表：**Table 1** ｜ 图：**Figure 2**（`skillbench_verification/figures/fig2_count_distribution_verified.pdf`）

| 指标 | GitHub（未复核） | SkillBench（审计原值） | SkillBench（**复核后**） |
|---|---:|---:|---:|
| Skill 数 | 488 | 87 | 87 |
| ≥1 条不一致 | 329 (67.4%) | 72 (82.8%) | **56 (64.4%)** |
| 零 finding | 159 (32.6%) | 15 (17.2%) | **31 (35.6%)** |
| Finding 总数 | 1,022 | 377 | **160** |
| Mean / skill | 2.09 | 4.33 | **1.84** |
| Median / skill | 1 | 3 | **1** |
| P90 / skill | 5 | 10 | **4** |
| Max / skill | 18 | 20 | **18** |

**可写入论文的陈述：**

> On the verified corpus, 56 of the 87 SkillBench tasks (64.4%) contain at least one confirmed
> contract inconsistency; 31 tasks (35.6%) are entirely free of them.

> Per-task counts are right-skewed: the median SkillBench task carries a single inconsistency and
> the 90th percentile carries four, with a maximum of 18. The median GitHub skill also carries a
> single inconsistency (P90 = 5), but the GitHub figures have not yet been verified and are an
> upper bound on the true rate.

> Verification materially changes the picture: the raw audit reported 72 of 87 tasks (82.8%) as
> affected with a mean of 4.33 inconsistencies per task; after rejecting findings that do not meet
> the contract-inconsistency definition the figures fall to 56 tasks (64.4%) and a mean of 1.84.
> We therefore report the verified counts throughout.

Figure 2 说明句：

> **Figure 2.** Distribution of confirmed inconsistencies per skill on a common axis, normalised to
> the share of each corpus. SkillBench uses the verified findings; the GitHub distribution is drawn
> hatched because it has not been verified. SkillBench is now markedly closer to GitHub than the raw
> audit suggested: both corpora have a median of one inconsistency and 33–36% of their skills at
> zero (GitHub 32.6%, SkillBench 35.6%), and only four SkillBench tasks exceed seven
> inconsistencies (against 19 GitHub skills).

### A.2 How dense?

| 指标 | GitHub（未复核） | SkillBench（审计原值） | SkillBench（**复核后**） |
|---|---:|---:|---:|
| Median contract claims / skill | 72 | 119 | 119 |
| Inconsistencies / 100 claims（median skill） | 1.55 | 1.79 | **0.59** |

> Normalised by the size of the declared contract, the verified SkillBench corpus exhibits a median
> of 0.59 inconsistencies per 100 contract claims. The corresponding GitHub figure (1.55) is an
> upper bound: the same checkers that inflated the SkillBench rate by a factor of three also
> produced the GitHub findings.

> **Writing note.** Do not use the earlier "the two corpora have comparable per-claim density"
> sentence — it was an artefact of unverified findings. See Finding 3.

### A.3 Severity and agent impact

数据：`skillbench_verification/outputs/verified/table2_impact_verified.csv` ｜ 表：**Table 2**

| | GitHub（未复核） | SkillBench（审计原值） | SkillBench（**复核后**） |
|---|---:|---:|---:|
| 确证阻断执行 | 44 (4.3%) | 41 (10.9%) | 27 (**16.9%**) |
| 产生静默错误 | 796 (77.9%) | 231 (61.3%) | 100 (62.5%) |

> Most inconsistencies remain silent: 62.5% of the verified SkillBench findings describe behaviour
> that is wrong without producing an observable failure. After verification the share that is
> confirmed to block execution rises to 16.9%, because the rejected findings were disproportionately
> speculative environment assumptions rather than hard execution blockers.

> **Writing note.** The "overall 73.4% silent / 6.1% blocking" figure in v1 mixed verified and
> unverified data and must be recomputed after the GitHub corpus is verified.

### A.4 Documentation-only skills vs skills with artifacts

图：**Figure 5**（`skillbench_verification/figures/fig5_doconly_vs_artifacts.pdf`，两个语料合并、只区分这两种情况）

口径：**documentation-only** = 该 skill 目录里除文档（`.md/.mdx/.rst/.txt/.org`）外没有任何文件；
**with artifacts** = 至少含一个非文档文件（脚本、配置、资源等）。

**两个语料的构成**（表：`skillbench_verification/outputs/verified/table8_skill_composition.tex`）

| Corpus | Documentation-only | With artifacts | Total |
|---|---:|---:|---:|
| GitHub Skills（未复核） | 340 (69.7%) | 148 (30.3%) | 488 |
| SkillBench | 41 (47.1%) | 46 (52.9%) | 87 |
| **Total** | **381 (66.3%)** | **194 (33.7%)** | **575** |

> More than two thirds of the sampled GitHub skills (340 of 488, 69.7%) ship nothing but
> documentation — a single `SKILL.md` in most cases — whereas SkillBench tasks are more evenly split
> (41 documentation-only, 46 with artifacts). Any comparison of inconsistency counts between the
> corpora is therefore also a comparison between two very different mixes of documentation-only and
> artifact-bearing skills.

**合并后的分布**（上表两种情况的 inconsistencies）：

| Group | n | findings | 受影响 | mean | median | P90 | max | 契约中位数 | 每 100 claims |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| documentation-only | 381 | 480 | 59.6% | 1.26 | 1 | 3 | 8 | 56 | 1.26 |
| with artifacts | 194 | 702 | **81.4%** | **3.62** | 3 | 8 | 18 | 169 | 1.45 |

**可写入论文的陈述：**

> **Figure 5.** Distribution of confirmed inconsistencies per skill for documentation-only skills
> ($n=381$) and for skills that ship artifacts ($n=194$), pooling both corpora on a common scale.
> Skills with artifacts are considerably more likely to be affected (81.4% vs 59.6%) and carry
> almost three times as many inconsistencies on average (3.62 vs 1.26); the shift holds across the
> whole distribution, with a 90th percentile of 8 against 3 and a tail that reaches 18.

> The gap largely disappears once contract size is taken into account. Skills with artifacts declare
> a median of 169 contract claims against 56 for documentation-only skills, and the two groups then
> differ by only 15% in inconsistencies per 100 claims (1.45 vs 1.26). Raw inconsistency counts
> therefore track how much contract surface a skill declares at least as much as whether it ships
> executable artifacts.

> **Caveat.** The pooled counts are dominated by the GitHub corpus, which contributes 86% of the
> findings and has not been verified (SkillBench uses the verified subset). Split by corpus the
> normalised effect even changes sign — GitHub 1.37 → 1.82, verified SkillBench 0.93 → 0.57 — so the
> pooled contrast should be read as an upper bound; a like-for-like comparison requires verifying the
> GitHub findings first.

分语料明细（用于上面的 caveat，也是复核前后差异的来源）：

| 分组 | n | 受影响 | mean | median | P90 | max | 契约中位数 | 每 100 claims |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GitHub · documentation-only | 340 | 59% | 1.24 | 1 | 3 | 7 | 52 | 1.37 |
| GitHub · with artifacts | 148 | 86% | 4.06 | 4 | 8 | 18 | 162 | 1.82 |
| SkillBench · documentation-only（复核后） | 41 | 61% | 1.44 | 1 | 3 | 8 | 106 | 0.93 |
| SkillBench · with artifacts（复核后） | 46 | 67% | 2.20 | 1 | 4 | 18 | 183 | 0.57 |

> The boundary mix does differ by group, and consistently so on the verified corpus: skills with
> artifacts are dominated by Document–Code (65.3% of their findings) while documentation-only tasks
> split almost evenly between Document–Document (42.4%) and Document–Code (40.7%). The dominant
> contract element is the same in both groups, however — capability (26–27%).

---

## B. Types of Inconsistencies

### B.1 Artifact boundary（Figure 3）

数据：`skillbench_verification/outputs/verified/table3_boundary_verified.csv` ｜ 表：**Table 3** ｜ 图：**Figure 3**（`skillbench_verification/figures/fig3_artifact_boundary_verified.pdf`）

| Artifact boundary | GitHub（未复核） | SkillBench（审计原值） | SkillBench（**复核后**） |
|---|---:|---:|---:|
| Document–Code | 344 (33.7%) | 178 (47.2%) | 90 (**56.2%**) |
| Document–Document | 312 (30.5%) | 74 (19.6%) | 45 (**28.1%**) |
| Skill–Environment | 366 (35.8%) | 125 (33.2%) | 25 (**15.6%**) |

> **Figure 3.** On the verified SkillBench corpus the Document–Code boundary dominates, accounting
> for 56.2% of all inconsistencies, followed by Document–Document (28.1%) and Skill–Environment
> (15.6%). Verification removes 80% of the environment-layer findings (125 → 25) but only 49% of
> the Document–Code findings, so the boundary mix is far more skewed than the raw audit suggested.

> The GitHub corpus presents a different mix — Skill–Environment 35.8%, Document–Code 33.7%,
> Document–Document 30.5% — but those findings are unverified and the environment layer is exactly
> where the audit is least reliable, so this comparison is provisional.

### B.2 Taxonomy 一二级合并分布（**primary table**）

数据：`skillbench_verification/outputs/verified/table7_taxonomy_l1_l2.csv`
表：**Table 3**（`table7_taxonomy_l1_l2.tex`，把 L1 与 L2 放在同一张表里）

| Artifact boundary (L1) | Inconsistency type (L2) | GitHub（未复核） | SkillBench（**复核后**） |
|---|---|---:|---:|
| **Document–Code** | `over_promised` | 250 (24.5%) | **73 (45.6%)** |
| | `semantic_conflict` | 93 (9.1%) | 16 (10.0%) |
| | `under_promised` | 1 (0.1%) | 1 (0.6%) |
| | *subtotal* | *344 (33.7%)* | *90 (56.2%)* |
| **Document–Document** | `shared_concept_definition_conflict` | 162 (15.9%) | 27 (16.9%) |
| | `cross_document_process_conflict` | 81 (7.9%) | 2 (1.2%) |
| | `interface_contract_mismatch` | 69 (6.8%) | 16 (10.0%) |
| | *subtotal* | *312 (30.5%)* | *45 (28.1%)* |
| **Skill–Environment** | `environment_fact_conflict` | 274 (26.8%) | 21 (13.1%) |
| | `external_resource_invalid` | 44 (4.3%) | 3 (1.9%) |
| | `external_service_contract_change` | 30 (2.9%) | 1 (0.6%) |
| | `dependency_version_drift` | 18 (1.8%) | **0 (0.0%)** |
| | *subtotal* | *366 (35.8%)* | *25 (15.6%)* |
| | **Total** | **1,022 (100.0%)** | **160 (100.0%)** |

排版说明：L1 用 `\multirow` 纵向合并，每个 boundary 的 L2 明细下面用 `\cmidrule(lr){2-4}` 分隔出 subtotal 行，
因此**不依赖加粗/斜体**也能读出层级（换任何字体都不会错版）。需要 `\usepackage{multirow}`，
外加 `booktabs`、`graphicx`（表格内置了只在超宽时收缩的 `\resizebox`）。

**可写入论文的陈述：**

> **Table 3.** Distribution of contract inconsistencies over the taxonomy: the artifact boundary at
> which the contract breaks (level 1) and the inconsistency type (level 2). GitHub findings are
> unverified; SkillBench uses the verified subset.

> Over-promised implementation contracts dominate the verified SkillBench corpus: 73 of the 160
> findings (45.6%) are cases in which the documentation promises more than the implementation
> delivers, and the Document–Code boundary as a whole accounts for 90 findings (56.2%).

> Verification reorders the type distribution. The raw audit ranked `environment_fact_conflict`
> second at 23.1% with `over_promised` at 39.5%; because 76% of the environment findings were
> rejected while `over_promised` survived at 49%, `over_promised` now leads by a factor of 3.5 and
> `dependency_version_drift` disappears entirely (16 audit findings, 0 survivors).

> The unverified GitHub corpus shows a different ordering, with `environment_fact_conflict` (26.8%)
> narrowly ahead of `over_promised` (24.5%). Because the environment layer is exactly where the
> audit is least reliable — 27.2% survival overall, with two checkers producing no surviving finding
> — this ordering should not be reported as a cross-corpus difference until the GitHub findings are
> verified.

*（`table3_boundary_verified.tex` 与 `table4_l2_verified.tex` 是上表的分组来源，作为机器可核验的中间产物保留；
正文只放这一张合并表即可，不必重复。子类型内部的排序沿用 Table 4 的规则：按 GitHub 频次降序。）*

### B.3 Contract element（supplementary）



> 这是把 L2/L3 再映射到"契约的哪一部分"的**派生视图**，不是 taxonomy 本身。
> 若正文已用 B.2 的二级分类，本表建议放 appendix 或直接删掉。

数据：`skillbench_verification/outputs/verified/table5_facet_verified.csv`

| Contract element | GitHub（未复核） | SkillBench（**复核后**） |
|---|---:|---:|
| capability | 153 (15.0%) | 42 (26.2%) |
| parameter | 57 (5.6%) | 26 (16.2%) |
| environment assumption | 274 (26.8%) | 25 (15.6%) |
| shared concept | 162 (15.9%) | 18 (11.2%) |
| interface / schema | 69 (6.8%) | 15 (9.4%) |
| return value | 49 (4.8%) | 11 (6.9%) |
| constraint / exception | 46 (4.5%) | 7 (4.4%) |
| external service contract | 30 (2.9%) | 5 (3.1%) |
| workflow | 109 (10.7%) | 4 (2.5%) |
| side effect | 11 (1.1%) | 3 (1.9%) |
| external resource | 44 (4.3%) | 3 (1.9%) |
| dependency version | 18 (1.8%) | 1 (0.6%) |

> The three dominant contract elements on the verified corpus — capability (26.2%), parameter
> (16.2%) and environment assumption (15.6%) — account for 58.0% of the findings.

### B.4 Boundary × 影响

数据由 `rq1_analysis/outputs/table5_boundary_impact.csv`（审计原值）给出；复核后需用
`verified/rq1_findings_verified.csv` 重算，**在 GitHub 复核完成前不建议单列此表**。

### B.5 三级 taxonomy（Appendix）

数据：`rq1_analysis/outputs/tableA1_l3_taxonomy.csv` ｜ 表：**Table A1**
（复核后请改用 `verified/rq1_findings_verified.csv` 重算，否则 appendix 与正文口径不一致。）

---

## C. Co-occurrence and Heterogeneity

> ⚠️ 本节受影响最大：复核后 SkillBench 的多 boundary 共现从 55.6% 掉到 **23.2%**，
> 而 GitHub 仍为 55.9%（未复核）。**"不一致性倾向于共现"这一结论目前只在未复核的 GitHub 上成立。**

### C.1 跨 boundary 共现

| 组 | GitHub（未复核） | SkillBench（审计原值） | SkillBench（**复核后**） |
|---|---:|---:|---:|
| 含 ≥1 finding 的 skill | 329 | 72 | 56 |
| 跨 ≥2 个 boundary | 184 (55.9%) | 40 (55.6%) | 13 (**23.2%**) |
| 跨全部 3 个 boundary | 66 (20.1%) | 13 (18.1%) | 1 (**1.8%**) |

P(boundary_j | boundary_i)：

| 条件 | GitHub（未复核） | SkillBench（**复核后**） |
|---|---:|---:|
| P(Skill–Env \| Doc–Code) | 0.60 | **0.08** |
| P(Doc–Doc \| Doc–Code) | 0.56 | 0.24 |
| P(Doc–Code \| Skill–Env) | 0.46 | 0.21 |
| P(Doc–Doc \| Skill–Env) | 0.52 | 0.21 |
| P(Doc–Code \| Doc–Doc) | 0.52 | 0.50 |
| P(Skill–Env \| Doc–Doc) | 0.63 | 0.17 |

> On the verified SkillBench corpus co-occurrence is moderate rather than the norm: 13 of the 56
> affected tasks (23.2%) violate two or more artifact boundaries and only one violates all three.
> The strongest conditional link is Document–Document → Document–Code (P = 0.50); every link that
> involves the environment layer falls below 0.25. This is in sharp contrast to the unverified
> GitHub corpus, where every cross-boundary conditional probability exceeds 0.46.

### C.2 最强 L2 共现对

数据：`rq1_analysis/outputs/table7_cooccurrence_pairs.csv`（基于审计原值）。
**该表必须在复核后重算**：GitHub 侧尚未复核，SkillBench 侧复核后样本量仅 160 条，
L2 共现对的稳定性会明显下降。在重算前不要把它写进论文。

### C.3 跨 domain 是否稳定

数据：`rq1_analysis/outputs/table8_domain_stability.csv`（审计原值）。同样需要按复核后数据重算；
且 software-engineering 域由未复核的 GitHub 语料主导（411/537），结论暂不可用。

---

## RQ1 Finding boxes（复核后重写）

> **Finding 1 — Contract inconsistencies are common in real skills, affecting roughly two thirds of
> both corpora, but they are neither universal nor strongly co-occurring.**
> After verification, 56 of 87 SkillBench tasks (64.4%) contain at least one confirmed contract
> inconsistency (median 1, P90 4); the unverified GitHub corpus shows a comparable prevalence of
> 67.4%, which we treat as an upper bound. Only 23.2% of the affected SkillBench tasks violate two
> or more artifact boundaries and just 1 of 56 violates all three — the "inconsistencies come in
> clusters" reading is not supported once findings are verified.

> **Finding 2 — The verified inconsistencies concentrate on the document–code boundary and on a
> single type: over-promising.**
> Document–Code accounts for 56.2% of the verified SkillBench findings, and at the taxonomy
> level-2 the distribution is dominated by `over_promised` (45.6%): the contract promises more than
> the implementation delivers. The remaining types form a shallow tail —
> `shared_concept_definition_conflict` (16.9%), `environment_fact_conflict` (13.1%),
> `interface_contract_mismatch` and `semantic_conflict` (10.0% each) — while three types
> (`under_promised`, `external_service_contract_change`, `dependency_version_drift`) contribute at
> most one finding each. Verification removes 80% of the environment-layer findings, so claims that
> "environment assumptions are the largest single source" are an artefact of unverified findings.
> 62.5% of the verified findings remain silent errors that no pass/fail test would catch.

> **Finding 3 — The apparent SkillBench-vs-GitHub gap in inconsistency load does not survive
> verification, and no cross-corpus claim should be made until the GitHub corpus is verified.**
> The raw audit reported 82.8% prevalence and 4.33 inconsistencies per SkillBench task, twice the
> GitHub rate; after verification SkillBench shows 64.4% and 1.84, i.e. a comparable regime
> (GitHub: 67.4% and 2.09, unverified upper bound). Because both corpora were produced by the same
> checkers, and because those checkers show a 57.6% rejection rate concentrated in the environment
> layer (0/14 and 0/7 for two of them), the only defensible statement today is that the two corpora
> are of similar order — and that a like-for-like comparison requires re-auditing or verifying the
> GitHub corpus.

---

## 附 A. SkillBench 复核结果摘要（可直接写进 Validity / Threats to Validity）

| 判定 | 数量 | 占比 |
|---|---:|---:|
| confirmed（真不一致 + 标签正确） | 120 | 31.8% |
| mislabeled（真不一致 + 标签错误） | 40 | 10.6% |
| invalid（不构成不一致） | 217 | 57.6% |

被否原因：`no_contradiction` 113、`speculation` 29、`not_a_contract` 27、`duplicate` 26、
`evidence_not_found` 21、`out_of_scope` 1。其中 **161 条属客观错误**，**56 条取决于口径**
（若把 `speculation` 计为有效，存活率上限为 50.1%）。

逐 checker 存活率：`impl_semantic_conflict_checker` 57.1%、`impl_over_promised_checker` 49.7%、
`doc_layer_checker` 48.6%、`env_layer_checker` 32.7%、`env_constraint_checker` **0/14**、
`url_validator` **0/7**、`schema_comparator` **0/1**。

证据质量：746 条引文中 506 条（67.8%）逐字一致、112 条行号漂移、98 条落在所引区间内、
**20 条引文在文件中不存在**、6 条为检查器合成消息。310/377 条 finding 的两侧引文全部逐字命中。

> **可用陈述：** "We manually and semi-automatically re-verified all 377 SkillBench findings and
> rejected 217 (57.6%) that do not meet the contract-inconsistency definition; the dominant failure
> modes are non-conflicting evidence (113), hypothetical environment scenarios (29) and quotations
> that do not contain a capability promise (27). Two of the seven checkers produced no surviving
> finding at all. All SkillBench results reported in this paper use the verified subset."

详细报告见 `SKILLBENCH_VERIFICATION_REPORT.md`，逐条判定见
`skillbench_verification/outputs/verification_results.csv`。

---

## 附 B. LaTeX 引用片段

```latex
% preamble（table7 合并表需要 multirow）
\usepackage{booktabs,makecell,array,graphicx,multirow}

% ---- A ----（三列对照版：GitHub 未复核 / SkillBench 审计原值 / SkillBench 复核后）
\input{skillbench_verification/outputs/verified/table1_prevalence_verified.tex}
\input{skillbench_verification/outputs/verified/table2_impact_verified.tex}

\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{skillbench_verification/figures/fig2_count_distribution_verified.pdf}
  \caption{Distribution of confirmed inconsistencies per skill ...}
  \label{fig:rq1-count}
\end{figure}

% ---- B ----
% Table 3: 一二级合并分布（推荐；已含 L1 subtotal）
\input{skillbench_verification/outputs/verified/table7_taxonomy_l1_l2.tex}
% 若正文只想要 L1 或只想要 L2，可改用下面两张机器产物（与上表同源）：
% \input{skillbench_verification/outputs/verified/table3_boundary_verified.tex}
% \input{skillbench_verification/outputs/verified/table4_l2_verified.tex}
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{skillbench_verification/figures/fig3_artifact_boundary_verified.pdf}
  \caption{Artifact boundary at which the skill contract breaks ...}
  \label{fig:rq1-boundary}
\end{figure}
% 二级分类的图（二选一，不要图表同上）
% \includegraphics[width=\linewidth]{skillbench_verification/figures/fig4_l2_types_verified.pdf}
\input{skillbench_verification/outputs/verified/table5_facet_verified.tex}   % supplementary

% ---- A.4 ----
\input{skillbench_verification/outputs/verified/table8_skill_composition.tex}
% \includegraphics[width=\linewidth]{skillbench_verification/figures/fig5_doconly_vs_artifacts.pdf}

% ---- C ----（复核后需重算，暂缓）
% \input{rq1_analysis/outputs/table6_cooccurrence_l1.tex}   % 审计原值，勿用
\input{skillbench_verification/outputs/verified/table6_cooccurrence_verified.tex}

% ---- appendix ----
\input{rq1_analysis/outputs/tableA1_l3_taxonomy.tex}   % 需按复核后数据重算
```

表格宽度（实测，单栏论文）：`table1–table5` 为 6–7 列，建议 ≥14 cm 栏宽；双栏论文请用 `table*` 跨栏。
`rq1_analysis/outputs/` 下的表沿用 v1 的宽度说明（12–16 cm 不等）。

---

## 附 C. 文件清单

```
rq1_analysis/                       基础统计（审计原值）
├── run_all.sh                      一键复现
├── build_dataset.py                → rq1_findings.csv / rq1_skills.csv
├── analyze_prevalence.py           → Table 1/2, Figure 2 数据
├── analyze_types.py                → Table 3/3b/4/5, Table A1
├── analyze_cooccurrence.py         → Table 6/6b/7/8
├── make_figures.py                 → figures/fig2..fig5
└── outputs/, figures/

skillbench_verification/            SkillBench 复核
├── verify_evidence.py              引文与磁盘逐字核对
├── build_verify_input.py           复核输入组装
├── aggregate_verification.py       → verification_results.csv / summary
├── apply_verification.py           ★ 复核后口径的 RQ1 统计
├── make_verified_figures.py        ★ 复核后的 Figure 2 / 3 / 4
├── figures/                        fig2_count_distribution_verified.*
│                                   fig3_artifact_boundary_verified.*
│                                   fig4_l2_types_verified.*
│                                   fig5_doconly_vs_artifacts.*
└── outputs/
    ├── verification_results.csv    ★ 逐 finding 判定 + 理由 + 修正标签
    └── verified/
        ├── rq1_findings_verified.csv   ★ 复核后的 finding 级数据（可直接喂给分析脚本）
        ├── table1_prevalence_verified.tex   流行度/密度（三列对照）
        ├── table2_impact_verified.tex       静默/阻断（三列对照）
        ├── table3_boundary_verified.tex     artifact boundary（三列对照）
        ├── table4_l2_verified.tex           ★ taxonomy 二级分类（三列对照）
        ├── table5_facet_verified.tex        contract element（补充视图）
        ├── table6_cooccurrence_verified.tex 共现（GitHub vs SkillBench 复核后）
        ├── table7_taxonomy_l1_l2.tex        ★ 一级+二级合并分布表
        ├── table8_skill_composition.tex     ★ 两语料的 doc-only / with-artifacts 构成
        └── summary.json
```

---

## 附 D. 仍需处理的事项

1. ~~重绘 Figure 2 与 Figure 3~~ **已完成**：见 `skillbench_verification/figures/*_verified.pdf`
   （GitHub 用斜线填充标记为未复核）。`rq1_analysis/figures/` 下的旧图仅供对照，不要再用。
2. **重算 C 节与 Table A1**：共现（Table 6/7/8）和三级 taxonomy 必须用复核后数据重算，
   否则正文与 appendix 口径冲突。
3. **GitHub 语料复核**：488 个 skill / 1022 条 finding 走同一套流程即可
   （`verify_evidence.py` 目前只扫 SkillBench，改一个常量即可复用）。
4. **是否采用宽松口径**：`speculation` 与 `not_a_contract` 共 56 条属口径相关，
   建议人工抽查后决定；若全部计入，SkillBench 存活率为 50.1%。
5. **修复审计器**：按 `SKILLBENCH_VERIFICATION_REPORT.md` 第 6 节的优先级修复 checker 后重跑，
   比在写作阶段做人工修正更彻底。
