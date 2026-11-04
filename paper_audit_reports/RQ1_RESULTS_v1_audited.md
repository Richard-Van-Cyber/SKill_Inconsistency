# RQ1 — Characterizing Skill Contract Inconsistencies · 数据与写作素材

本文件是 RQ1 的**结果底稿**：每个小节给出「要回答的问题 → 数据 → 图/表 → 可直接写进论文的英文陈述句」，
最后是 3 个 Finding box。所有数字均由 `rq1_analysis/` 下的脚本从审计报告直接算出，改数据后重跑即可更新。

```bash
cd paper_audit_reports/rq1_analysis
bash run_all.sh          # 5 步：建数据集 → 流行度/密度 → 类型 → 共现 → 出图
```

---

## 0. 数据与口径（写 Methods / 脚注用）

**语料**

| 语料 | 来源 | Skill 数 | Finding 数 |
|---|---|---|---|
| GitHub Skills | `wildskills_audit/`，公开 GitHub 仓库中采样的社区 Skill | 488 | 1,022 |
| SkillBench | `skillbench_audit/`，SkillBench 基准任务内置 Skill | 87 | 377 |
| **合计** | | **575** | **1,399** |

**Finding 口径**：审计报告 `findings[]` 中通过硬规则与 LLM 校验后保留的条目
（`validation_status ∈ {confirmed, hard_rule}`），已剔除被 suppress 的假阳性。

**Contract claim（密度分母）**：一个 Skill 的契约声明量 = 文档声明 + 代码接口声明。
- 文档声明：`.md/.mdx/.rst/.txt/.org` 中，剥离 frontmatter、标题、代码块后的**句子、列表项、表格行**；
- 代码接口声明：`.py/.js/.ts/.go/.rs/.java...` 中的**函数定义数 + 形参个数**；
- `Inconsistencies / 100 claims` = finding 数 ÷ contract claim 数 × 100。

**Artifact boundary（taxonomy L1）**：`Document–Code`（实现层）、`Document–Document`（文档层）、
`Skill–Environment`（环境层）。

**Contract element（facet）**：实现层用 L3，其余用 L2 映射到"契约的哪一部分"：
parameter / return / capability / constraint / side_effect / workflow / interface / concept /
resource / dependency / service contract / environment。

> ⚠️ 两个语料不可直接当作"质量对比"：SkillBench 是人工构造的基准任务，GitHub Skills 是社区采样。
> 二者的差异同时反映**任务性质**与**实现丰富度**，不要写成 "SkillBench 更差"。

---

## A. Prevalence and Density

### A.1 How prevalent?

数据：`outputs/table1_prevalence.csv` ｜ 表：**Table 1** ｜ 图：**Figure 2**（`figures/fig2_count_distribution.pdf`）

| 指标 | GitHub Skills | SkillBench |
|---|---:|---:|
| Skill 数 | 488 | 87 |
| ≥1 个 inconsistency | **329 (67.4%)** | **72 (82.8%)** |
| 零 finding | 159 (32.6%) | 15 (17.2%) |
| Finding 总数 | 1,022 | 377 |
| Mean / skill | 2.09 | 4.33 |
| Median / skill | 1 | 3 |
| P90 / skill | 5 | 10 |
| Max / skill | 18 | 20 |

**可写入论文的陈述：**

> Contract inconsistencies are pervasive in both corpora: 329 of the 488 GitHub skills (67.4%)
> and 72 of the 87 SkillBench tasks (82.8%) contain at least one confirmed inconsistency.

> The per-skill counts are strongly right-skewed. The median GitHub skill carries a single
> inconsistency while the median SkillBench task carries three; the 90th percentile reaches
> 5 and 10 respectively, and the maximum observed count is 18 (GitHub) and 20 (SkillBench).

> Inconsistency accumulation is therefore the norm rather than the exception: roughly one in
> three GitHub skills (159, 32.6%) is entirely clean, whereas only one in six SkillBench tasks
> (15, 17.2%) is.

Figure 2 说明句：

> **Figure 2.** Distribution of the number of confirmed inconsistencies per skill, on a common
> axis and normalised to the share of each corpus. GitHub skills are dominated by low counts
> (0–2, 68.4% of the corpus) with a long right tail; SkillBench is shifted to the right and
> remains non-negligible out to 12.

*(占比核对：GitHub 0–2 = 159+102+73 = 334/488 = 68.4%；SkillBench 0–2 = 15+14+7 = 36/87 = 41.4%。)*

### A.2 How dense?

| 指标 | GitHub Skills | SkillBench |
|---|---:|---:|
| Median contract claims / skill | 72 | 119 |
| Inconsistencies / 100 claims（**median skill**，主指标） | **1.55** | **1.79** |
| Inconsistencies / 100 claims（pooled） | 0.71 | 1.58 |
| 含代码的 skill | 126 (25.8%) | 42 (48.3%) |
| Inconsistencies / 100 LOC（median，仅含代码 skill） | 1.11 | 1.36 |

**可写入论文的陈述：**

> Once contract size is accounted for, the two corpora are comparable: the median skill
> exhibits 1.55 (GitHub) and 1.79 (SkillBench) inconsistencies per 100 contract claims.
> Among skills that ship executable code the median density is 1.11 and 1.36 per 100 LOC.

> The gap in absolute counts is driven by contract size and implementation richness rather
> than by a higher per-claim defect rate: SkillBench skills declare 65% more contract claims
> (median 119 vs 72) and are almost twice as likely to ship code (48.3% vs 25.8%).

> Only a quarter of the GitHub skills (126, 25.8%) contain executable code; the rest are
> documentation-only, so their implementation-layer contract can only be judged against the
> (absent) implementation.

*(写法建议：main text 用 median-skill 密度作为主指标，pooled 值放脚注——pooled 会被极少数超大型
代码仓库拉低，GitHub 侧最极端的一个 skill 就带 351,877 行代码。)*

### A.3 Severity and agent impact

数据：`outputs/table2_severity_impact.csv` ｜ 表：**Table 2**

| | GitHub Skills | SkillBench |
|---|---:|---:|
| Critical | 7 (0.7%) | 2 (0.5%) |
| High | 204 (20.0%) | 115 (30.5%) |
| Medium | 574 (56.2%) | 178 (47.2%) |
| Low | 237 (23.2%) | 82 (21.8%) |
| 确证阻断执行 | 44 (4.3%) | 41 (10.9%) |
| 产生静默错误 | 796 (**77.9%**) | 231 (61.3%) |

> Most inconsistencies are silent: 73.4% of all 1,399 findings describe behaviour that is
> wrong without producing an observable failure, whereas only 6.1% are confirmed to block
> execution. Agents therefore complete execution successfully while acting on a contract that
> does not hold, which makes these defects invisible to pass/fail evaluation.

---

## B. Types of Inconsistencies

### B.1 Artifact boundary（Figure 3）

数据：`outputs/table3_artifact_boundary.csv` ｜ 表：**Table 3** ｜ 图：**Figure 3**（`figures/fig3_artifact_boundary.pdf`）

| Artifact boundary | GitHub Skills | SkillBench | 合计 |
|---|---:|---:|---:|
| Skill–Environment | 366 (35.8%) | 125 (33.2%) | 491 (35.1%) |
| Document–Code | 344 (33.7%) | 178 (**47.2%**) | 522 (37.3%) |
| Document–Document | 312 (30.5%) | 74 (19.6%) | 386 (27.6%) |
| Total | 1,022 | 377 | 1,399 |

> **Figure 3.** Where the skill contract breaks. In GitHub skills the three artifact boundaries
> are nearly balanced (35.8% / 33.7% / 30.5%), i.e. no single surface monopolises
> inconsistencies. SkillBench is dominated by the Document–Code boundary (47.2%) and shows a
> markedly smaller share of Document–Document conflicts (19.6%).

> Pooling both corpora, the Document–Code and Skill–Environment boundaries together account
> for 72.4% of all findings.

**按是否含代码拆分**（`outputs/table3b_boundary_by_code.csv`）：

| Skill 内容 | Skill–Env | Doc–Code | Doc–Doc |
|---|---:|---:|---:|
| 含可执行代码（771 findings） | 36.1% | 38.8% | 25.2% |
| 纯文档（628 findings） | 33.9% | 35.5% | 30.6% |

> Documentation-only skills still attract Document–Code findings, because a capability that
> is promised in the contract and never implemented is itself a contract violation: 112 of the
> 223 Document–Code findings in code-free skills are `unimplemented_feature`.

### B.2 Contract element（secondary table）

数据：`outputs/table4_contract_facet.csv` ｜ 表：**Table 4** ｜ 图：**Figure 4**（可选，`figures/fig4_contract_facets.pdf`）

| Contract element | GitHub Skills | SkillBench | 合计 |
|---|---:|---:|---:|
| environment assumption | 274 (26.8%) | 87 (23.1%) | 361 (**25.8%**) |
| capability | 153 (15.0%) | 87 (23.1%) | 240 (**17.2%**) |
| shared concept | 162 (15.9%) | 40 (10.6%) | 202 (**14.4%**) |
| workflow | 109 (10.7%) | 7 (1.9%) | 116 (8.3%) |
| interface / schema | 69 (6.8%) | 29 (7.7%) | 98 (7.0%) |
| parameter | 57 (5.6%) | 38 (10.1%) | 95 (6.8%) |
| return value | 49 (4.8%) | 25 (6.6%) | 74 (5.3%) |
| constraint / exception | 46 (4.5%) | 21 (5.6%) | 67 (4.8%) |
| external resource | 44 (4.3%) | 12 (3.2%) | 56 (4.0%) |
| external service contract | 30 (2.9%) | 10 (2.7%) | 40 (2.9%) |
| dependency version | 18 (1.8%) | 16 (4.2%) | 34 (2.4%) |
| side effect | 11 (1.1%) | 5 (1.3%) | 16 (1.1%) |

> Three contract elements dominate: environment assumptions (25.8%), capabilities (17.2%) and
> shared concept definitions (14.4%); together they account for 57.4% of all findings.
> Parameter, return-value and workflow contracts are an order of magnitude rarer
> (6.8%, 5.3% and 8.3% respectively).

> The element mix also separates the corpora: workflow conflicts are 5.6x more frequent in
> GitHub skills (10.7% vs 1.9%), while parameter and dependency conflicts are roughly twice
> as frequent in SkillBench (10.1% vs 5.6%; 4.2% vs 1.8%).

### B.3 Boundary × 影响（Table 5）

| Artifact boundary | Findings | 阻断执行 | 静默错误 |
|---|---:|---:|---:|
| Skill–Environment | 491 | 50 (**10.2%**) | 290 (59.1%) |
| Document–Code | 522 | 34 (6.5%) | 382 (73.2%) |
| Document–Document | 386 | 1 (0.3%) | 355 (**92.0%**) |

> Frequency and severity point in opposite directions. Document–Document conflicts are the
> most silent (92.0% produce no observable failure) but almost never block execution (0.3%),
> whereas Skill–Environment conflicts are the most likely to abort a run (10.2%).

### B.4 三级 taxonomy（Appendix）

数据：`outputs/tableA1_l3_taxonomy.csv` ｜ 表：**Table A1**（`\footnotesize`，直接在 appendix `\input`）

---

## C. Co-occurrence and Heterogeneity（保持简短）

### C.1 跨 boundary 共现

数据：`outputs/table6_cooccurrence_l1.csv`、`outputs/table6b_multiboundary.csv` ｜ 表：**Table 6** ｜ 图：**Figure 5**（可选热力图）

在 401 个含 ≥1 inconsistency 的 skill 中：

| 组 | Skills | 占比 |
|---|---:|---:|
| 含 ≥1 inconsistency | 401 | 100.0% |
| 跨 ≥2 个 boundary | **224** | **55.9%** |
| 跨全部 3 个 boundary | 77 | 19.2% |

P(boundary_j | boundary_i)（两语料合并）：

| 条件 | P(Doc–Code \| ·) | P(Doc–Doc \| ·) | P(Skill–Env \| ·) |
|---|---:|---:|---:|
| 已知 Skill–Environment | 0.48 | 0.49 | — |
| 已知 Document–Code | — | 0.52 | 0.60 |
| 已知 Document–Document | 0.54 | — | 0.63 |

> Co-occurrence is the norm rather than the exception: of the 401 skills that contain at least
> one inconsistency, 224 (55.9%) violate two or more artifact boundaries simultaneously and
> 77 (19.2%) violate all three.

> Every cross-boundary conditional probability exceeds 0.35 and most exceed 0.5: 60% of skills
> with a Document–Code finding also carry a Skill–Environment finding, and 63% of skills with a
> Document–Document finding also carry a Skill–Environment finding.

### C.2 最强 L2 共现对（Table 7）

| Type i | Type j | 共现 skill 数 | P(j\|i) | P(i\|j) |
|---|---|---:|---:|---:|
| `over_promised` | `environment_fact_conflict` | **96** | 0.53 | 0.42 |
| `environment_fact_conflict` | `shared_concept_definition_conflict` | 81 | 0.36 | 0.58 |
| `over_promised` | `shared_concept_definition_conflict` | 73 | 0.40 | 0.53 |
| `environment_fact_conflict` | `semantic_conflict` | 54 | 0.24 | 0.65 |
| `environment_fact_conflict` | `interface_contract_mismatch` | 46 | 0.20 | 0.62 |
| `environment_fact_conflict` | `dependency_version_drift` | 23 | 0.10 | 0.72 |

> At level-2 granularity the dominant pair is `over_promised` + `environment_fact_conflict`,
> which co-occurs in 96 skills. `environment_fact_conflict` appears in five of the six
> strongest pairs and acts as a hub: the conditional probability that a skill carrying a
> semantic, interface or dependency conflict also has an environment assumption error is
> 0.62–0.72.

### C.3 跨 domain 是否稳定（Table 8）

| Domain | Skills | Findings | Skill–Env | Doc–Code | Doc–Doc | ≥2 boundaries |
|---|---:|---:|---:|---:|---:|---:|
| software-engineering | 411 | 808 | 36.5% | 32.7% | 30.8% | 52.6% |
| media-content-production | 41 | 142 | 28.9% | 46.5% | 24.6% | 71.0% |
| office-white-collar | 38 | 129 | 35.7% | 41.1% | 23.3% | 58.6% |
| finance-economics | 27 | 105 | 41.9% | 32.4% | 25.7% | 65.2% |
| natural-science | 20 | 61 | 32.8% | 52.5% | 14.8% | 60.0% |

> Stratified by domain (five domains with at least 20 audited skills), multi-boundary
> co-occurrence remains high everywhere — between 52.6% and 71.0% of skills span two or more
> boundaries — so the co-occurrence structure is a property of skill contracts rather than an
> artefact of one domain. The boundary *mix*, however, is not stable: the Document–Code share
> ranges from 32.7% (software engineering) to 52.5% (natural science).

*(口径提醒：domain 标签来自 `paper_audit_reports/skill_category_distribution.csv`，两语料共用同一套 8 类；
software-engineering 由 GitHub 语料主导（411/537），写进论文时建议注明。)*

---

## RQ1 Finding boxes（3 条，直接可用）

> **Finding 1 — Contract inconsistencies are pervasive and frequently co-occur within
> individual Agent Skills.**
> 329 of 488 GitHub skills (67.4%) and 72 of 87 SkillBench tasks (82.8%) contain at least one
> confirmed inconsistency, with a median of 1 and 3 respectively and a 90th percentile of 5
> and 10. Among skills that contain any inconsistency, 224 of 401 (55.9%) violate two or more
> artifact boundaries simultaneously and 77 (19.2%) violate all three. 73.4% of all 1,399
> findings produce a silent error rather than an observable failure, so inconsistency
> accumulation is invisible to conventional pass/fail evaluation.

> **Finding 2 — Inconsistencies concentrate on a few contract surfaces rather than spreading
> uniformly.**
> Two of the three artifact boundaries — Document–Code and Skill–Environment — account for
> 72.4% of all findings, and three contract elements (environment assumptions, capabilities
> and shared concept definitions) account for 57.4%. The concentration matters because the
> surfaces differ in how they fail: 92.0% of Document–Document findings are silent but only
> 0.3% block execution, whereas Skill–Environment findings block execution in 10.2% of cases —
> a 34x difference in hard-failure rate despite a smaller share of findings.

> **Finding 3 — SkillBench exhibits the same qualitative structure as popular GitHub skills,
> but roughly twice the inconsistency load.**
> Both corpora share the cross-boundary co-occurrence structure (all conditional probabilities
> ≥ 0.35) and a comparable per-claim density (median 1.79 vs 1.55 inconsistencies per 100
> contract claims). SkillBench tasks nevertheless carry 2.1x the mean number of
> inconsistencies (4.33 vs 2.09) and 2x the P90 (10 vs 5), because their contracts are larger
> (median 119 vs 72 claims) and almost twice as likely to ship executable code (48.3% vs
> 25.8%). The type mix shifts accordingly: Document–Code rises from 33.7% to 47.2% while
> Document–Document falls from 30.5% to 19.6%.

---

## LaTeX 引用片段

```latex
% preamble
\usepackage{booktabs,makecell,array,graphicx}

% ---- A ----
\input{outputs/table1_prevalence.tex}        % Table 1
\input{outputs/table2_severity_impact.tex}   % Table 2 (severity / impact)

\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{figures/fig2_count_distribution.pdf}
  \caption{Distribution of confirmed inconsistencies per skill ...}
  \label{fig:rq1-count}
\end{figure}

% ---- B ----
\input{outputs/table3_artifact_boundary.tex} % Table 3
\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{figures/fig3_artifact_boundary.pdf}
  \caption{Artifact boundary at which the skill contract breaks ...}
  \label{fig:rq1-boundary}
\end{figure}
\input{outputs/table4_contract_facet.tex}    % Table 4 (secondary, contract element)
\input{outputs/table5_boundary_impact.tex}   % Table 5

% ---- C ----
\input{outputs/table6_cooccurrence_l1.tex}   % Table 6
\input{outputs/table6b_multiboundary.tex}
\input{outputs/table7_cooccurrence_pairs.tex}
\input{outputs/table8_domain_stability.tex}

% ---- appendix ----
\input{outputs/tableA1_l3_taxonomy.tex}
% 可选图：figures/fig4_contract_facets.pdf, figures/fig5_cooccurrence.pdf
```

表格文件均为完整 `table` 环境（含 caption / label），直接 `\input` 即可。已用 tectonic 逐表编译验证：**0 error**。
单栏正文宽度与表格适配情况（实测）：

| 表格 | 12 cm | 13 cm | 14 cm | 15 cm |
|---|---|---|---|---|
| Table 2 / 3b / 5 / 6 / 6b / 8 / A1 | ✅ | ✅ | ✅ | ✅ |
| Table 1（流行度/密度） | — | ✅ | ✅ | ✅ |
| Table 3 / 4（boundary / contract element） | — | — | ✅ | ✅ |
| Table 7（L2 共现对） | — | — | — | ✅ |

- Table 8 与 Table A1 内置了 `\resizebox` 自动收缩保护（只在超宽时缩小，不会放大），12 cm 栏宽下也能放下；
  因此**必须加载 `graphicx`**，其余表格不需要。
- 如果是**双栏论文**：上表中标 `—` 的宽表请用 `table*` 跨栏放置；窄表（Table 2/3b/5/6/6b）可直接放单栏。

---

## 文件清单

```
rq1_analysis/
├── run_all.sh                    一键复现
├── rq1_lib.py                    语料定义、taxonomy 映射、contract claim 计数、绘图样式
├── build_dataset.py              → outputs/rq1_findings.csv, rq1_skills.csv
├── analyze_prevalence.py         → Table 1/2, Figure 2 数据, rq1_stats.json
├── analyze_types.py              → Table 3/3b/4/5, Table A1, Figure 3/4 数据
├── analyze_cooccurrence.py       → Table 6/6b/7/8, Figure 5 数据
├── make_figures.py               → figures/fig2..fig5 (.pdf + .png)
├── outputs/                      11 个 csv + 11 个 tex + stats.json
└── figures/                      4 张图，pdf 供 LaTeX，png 供预览
```

## 需要你确认的三点

1. **Contract claim 的定义**是否接受（文档句子/列表/表格行 + 代码函数与形参）。若你想换成
   "auditor 识别出的 contract component 数"（`skill_map_summary.components`，均值 16.6），
   改 `rq1_lib.measure_skill` 一个函数即可，全流程会自动重算。
2. **两个语料的称呼**：目前用 "GitHub Skills" 与 "SkillBench"；若论文里叫 WildSkills，改
   `rq1_lib.CORPORA` 里的 `label` 即可，图和表会同步更新。
3. **domain 稳定性**目前混用了两个语料；若只想看 GitHub 语料，在 `analyze_cooccurrence.py`
   的 domain 部分加一行 `fb = fb[fb.corpus == "wildskills"]`。
