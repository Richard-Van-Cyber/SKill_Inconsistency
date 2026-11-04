# SkillBench 审计 Findings 复核报告

**复核对象**：`paper_audit_reports/skillbench_audit/` 下 87 个任务、377 条 findings
**复核时间**：2026-09-28 ｜ **产物**：`paper_audit_reports/skillbench_verification/`

---

## 0. 结论摘要

| | 数量 | 占比 |
|---|---:|---:|
| 确证（是真不一致性，标签也对） | **120** | 31.8% |
| 标签错误但确有其事（mislabeled） | **40** | 10.6% |
| **合计可用** | **160** | **42.4%** |
| 不是我们定义的不一致性（invalid） | **217** | 57.6% |

- **超过一半的 SkillBench finding 站不住**。两次独立复核运行给出 invalid 203 / 217（53.8% / 57.6%），结论稳定。
- **环境层是重灾区**：存活率仅 27.2%，而实现层 50.6%、文档层 48.6%。
- **三个 checker 全军覆没**：`env_constraint_checker` 0/14、`url_validator` 0/7、`schema_comparator` 0/1。
- **证据本身也不可靠**：746 条引文中只有 506 条（67.8%）与文件逐字一致；112 条行号漂移；20 条引文在文件中**根本不存在**；6 条是检查器合成的假引文。
- **RQ1 的 SkillBench 数字需要整体下调**：prevalence 82.8% → 56.3%（严）/ 64.4%（宽）；findings 377 → 120 / 160；mean 4.33 → 1.38 / 1.84；P90 10 → 3 / 4；artifact boundary 分布里 Skill–Environment 从 33.2% 跌到 15.0%。

---

## 1. 复核方法（三层）

**第一层 · 机械证据核对**（`verify_evidence.py`）
对每一条 finding 的 source_a / source_b 引文，在磁盘上定位其引用的文件（支持路径前缀纠错与 basename 兜底），逐字比对引文与所引行区间：

| 状态 | 含义 | 条数 | 占比 |
|---|---|---:|---:|
| `exact` | 引文 == 所引行 | 506 | 67.8% |
| `in_range` | 引文出现在所引区间内 | 98 | 13.1% |
| `drifted` | 文字确实在文件里，但行号漂移 | 112 | 15.0% |
| `not_found` | 引文在该文件中找不到 | 20 | 2.7% |
| `placeholder` | 文件名字段是合成占位（如 `<code literal>`） | 6 | 0.8% |
| `range_in_span` | 所引区间是引文的子集 | 4 | 0.5% |

310/377 条 finding 的两侧引文全部逐字命中；漂移中位数为 −5 行，但 36 条漂移超过 20 行。

**第二层 · 独立语义复核**（workflow，19 批 × 20 条）
每条 finding 连同**磁盘上真实文件内容**（非审计时的引文）交给独立 agent，按论文定义判定：

> 一个 finding 成立，当且仅当 (1) 两个契约制品真实互相矛盾（文档↔代码 / 文档↔文档 / 声明↔环境事实）；(2) 矛盾可由证据证实；(3) 矛盾针对该技能自身的契约，而非泛泛叙述、条件式假设或风格问题。

判定为 `confirmed` / `mislabeled`（确有其事但层级或类型标错，需给出正确标签）/ `invalid`（并给出原因码）/ `unverifiable`。

**第三层 · 对抗裁定**（workflow，13 批）
所有非 confirmed 的 finding 交给新 agent 从零重审，要求双向对抗：既不橡皮图章，也不"抢救"证据不成立的条目。本轮裁定未推翻任何一条（说明第一层判定本身已足够保守；但两次独立运行的差异见 §7）。

复现：

```bash
cd paper_audit_reports/skillbench_verification
python3 verify_evidence.py        # 第一层，机械核对
python3 build_verify_input.py     # 组装复核输入（含真实文件内容）
# 第二、三层由 workflow 执行（见本次会话），结果落在 outputs/verdicts/
python3 aggregate_verification.py # 汇总 + 对 RQ1 的影响
```

---

## 2. 被否定的原因分布

| 原因码 | 条数 | 性质 |
|---|---:|---|
| `no_contradiction` | 113 | **客观**：两侧其实并不矛盾（省略、互补、作用域已限定） |
| `duplicate` | 26 | **客观**：与同一 skill 内另一条 finding 是同一根因 |
| `evidence_not_found` | 21 | **客观**：引文不存在 / 是合成消息 |
| `out_of_scope` | 1 | **客观** |
| `speculation` | 29 | **口径相关**：只有在假设场景下才成立（未发生的版本、别的发行版、畸形输入） |
| `not_a_contract` | 27 | **口径相关**：被引文字是给 Agent 的方法学指引/散文/示例占位，不是对能力的承诺 |

即：**161 条可以直接丢弃**（客观错误），**56 条取决于你对"契约"的口径**。若把 `speculation` 全部算作有效，存活率上限为 (160+29)/377 = **50.1%**。

---

## 3. 逐层与逐 checker 存活率

| 声称层级 | 总数 | confirmed | mislabeled | invalid | 存活率 |
|---|---:|---:|---:|---:|---:|
| implementation | 178 | 72 | 18 | 88 | 50.6% |
| document | 74 | 30 | 6 | 38 | 48.6% |
| environmental | 125 | 18 | 16 | 91 | **27.2%** |

| 产出该 finding 的 checker | 总数 | confirmed | mislabeled | invalid | 存活率 |
|---|---:|---:|---:|---:|---:|
| `impl_semantic_conflict_checker` | 28 | 12 | 4 | 12 | **57.1%** |
| `impl_over_promised_checker` | 149 | 60 | 14 | 75 | 49.7% |
| `doc_layer_checker` | 74 | 30 | 6 | 38 | 48.6% |
| `env_layer_checker` | 104 | 18 | 16 | 70 | 32.7% |
| `env_constraint_checker` | 14 | 0 | 0 | 14 | **0.0%** |
| `url_validator` | 7 | 0 | 0 | 7 | **0.0%** |
| `schema_comparator` | 1 | 0 | 0 | 1 | **0.0%** |

按 L2 看，最不可信的是 `dependency_version_drift`（16 条只活 1 条，6.2%）与 `environment_fact_conflict`（87 条活 25 条，28.7%）。

---

## 4. 系统性缺陷（附实证）

### 4.1 `env_constraint_checker`：合成证据 + 层级错标（0/14）

它的 `span_text` 是程序生成的字符串 `Code performs file writes or global state mutations (detected via AST analysis)`，根本不是文件里的代码；而对应的 finding 却被打成 **environmental / environment_fact_conflict**——按 taxonomy，代码写文件/改全局状态属于 **implementation / semantic_conflict / side_effect_conflict**。

> 例：`shock-analysis-supply|F-005`、`financial-modeling-qa|F-001`、`pdf-excel-diff|F-001`、`organize-messy-files|F-009`。
> `pdf-excel-diff|F-001` 的源文件 `check_bounding_boxes.py` 实际没有任何写操作——证据与结论都是错的。

**修复**：要么删除该 checker，要么改标为 `side_effect_conflict` 并要求真实代码 span。

### 4.2 `url_validator`：把命名空间标识符当活链接探测（0/7）

7 条全部是假阳性，而且是同一种错法——把 **XML 命名空间字符串**或**模板占位 URL** 当成 HTTP 端点去请求，拿到 404/405 就判定"外部资源失效"：

> `organize-messy-files|F-003`：URL 出自 `document.py` 的 `setAttribute('xmlns:w14', …)`，代码里没有任何 HTTP 调用。
> `pptx-reference-formatting|F-001` / `exceltable-in-ppt|F-002` / `fix-druid-loophole-cve|F-003`：URL 是 `OOXML_NAMESPACES` 常量。
> `fix-build-agentops|F-001`：`https://github.com/user/project.git` 是通用 `git clone` 示例里的占位符。
> `citation-check|F-009`：checker 用裸 URL 探测得到 405，而代码真实调用带 `db=pubmed&id=…` 参数、实际返回 200。

**修复**：只对 AST 中真实的网络调用目标做校验，并用代码实际的参数重放请求；跳过 `xmlns`/命名空间/占位符。

### 4.3 `dependency_version_drift`：没有声明版本却在推断漂移（1/16）

15 条被否的条目的共同模式是：**技能根本没有声明任何依赖版本**，checker 却根据"较新/较旧版本会挂"来判定漂移；而任务镜像其实已在 Dockerfile 里固定了版本。

> `earthquake-plate-calculation|F-003`：`unary_union` 在固定的 geopandas 1.0.1 里只是 DeprecationWarning，技能也没 pin 版本。
> `r2r-mpc-control|F-003`、`radar-vital-signs|F-001`、`threejs-to-obj|F-008`、`paratransit-routing|F-002`、`offer-letter-generator|F-006`：镜像已固定 numpy/scipy/three/python-docx/ortools 版本，API 均可用。
> `flood-risk-analysis|F-005`、`multilingual-video-dubbing|F-001/008`：对"别的版本/别的发行版"的假设。

**修复**：只有契约里出现版本约束时才允许触发；触发前必须核对任务镜像实际安装的版本。

### 4.4 `env_layer_checker`：把"假设场景"当环境事实（存活 32.7%）

典型是被否的 `speculation`：只有在技能运行环境之外的情形下才成立。

> `3d-scan-calc|F-001`：文档说"自动处理 Binary STL"，代码用严格文件大小断言；但本任务的 `scan_data.stl` 恰好是 17684 字节 = 84 + 50×352（已核对），所以"冲突"没有实现。
> `organize-messy-files|F-008`：`process.platform === 'darwin'` 分支在 Linux 沙箱里永不执行。
> `earthquake-plate-calculation|F-002`：断言"环境未预装 geopandas"，而该任务的 Dockerfile 明确安装了 `geopandas==1.0.1`（已核对）。

**修复**：环境事实类判定必须绑定 task 的 Dockerfile / task.md 实际环境，禁止以"如果部署在别的环境"为据。

### 4.5 重复计数（26 条）

同一个根因被不同 checker 或不同角度重复报告，例如：

> `shock-analysis-demand|F-002` 与 `F-003`；`fix-visual-stability|F-004`、`F-005` 与 `F-006`（同一处 CDP 字段假设被拆成三条）。

**修复**：按 `root_cause_id` 合并；无该字段时用 (file, line, 语义) 去重。注意：**存活下来的 160 条本身没有重复**（160 条 finding ↔ 160 个不同 root cause）。

### 4.6 证据精度（112 条行号漂移、20 条引文不存在）

引文内容大多真实存在，但行号经常错位；另有 20 条引文在文件里完全找不到（含 6 条合成消息、若干被"改写"过的引文，如把 `- **RPKI origin validation** — …` 引成 `RPKI origin validation — …`）。

**修复**：落盘前用引文反查行号并回写；对找不到的引文直接丢弃该 finding。

### 4.7 层级误标（40 条）

| 声称层级 → 修正层级 | 条数 |
|---|---:|
| environmental → implementation | 10 |
| implementation → document | 9 |
| implementation → environmental | 7 |
| environmental → document | 6 |
| document → implementation | 6 |
| implementation → implementation（L3 错） | 2 |

> `data-to-d3|F-001`、`earthquake-plate-calculation|F-005` 实为同一文档内部两处陈述冲突（document/shared_concept_definition_conflict 与 document/interface_contract_mismatch），却被标成 environmental。
> `dialogue-parser|F-001/F-005`：`validate()` 返回格式的文档↔代码不符被标成 document / external_service_contract_change，实为 implementation / over_promised / missing_return_field。

**修复**：在 checker prompt 里加"层级判定决策树"，并要求给出被引两端的制品类型（doc / code / env）。

---

## 5. 对 RQ1 数字的影响

**SkillBench 侧（分母固定为全部 87 个任务）**

| 指标 | 审计原值 | 仅 confirmed | confirmed + 重标 |
|---|---:|---:|---:|
| 至少 1 条不一致的任务数 | 72 | 49 | 56 |
| prevalence | 82.8% | **56.3%** | **64.4%** |
| finding 总数 | 377 | **120** | **160** |
| mean / task | 4.33 | 1.38 | 1.84 |
| median / task | 3 | 1 | 1 |
| P90 / task | 10 | 3 | 4 |
| max / task | 20 | 14 | 18 |

**Artifact boundary 分布（占 finding 比例）**

| 层级 | 审计原值 | 仅 confirmed | confirmed + 重标 |
|---|---:|---:|---:|
| Document–Code | 47.2% | 60.0% | 56.2% |
| Skill–Environment | 33.2% | **15.0%** | **15.6%** |
| Document–Document | 19.6% | 25.0% | 28.1% |

结论方向性变化：**环境层被严重高估**。SkillBench 上"三个 boundary 相对均衡"的说法不成立——Document–Code 才是主导（56–60%），环境层只有 15%。

**GitHub 语料未在本轮复核范围内**，但如果环境层存在同样的假阳性模式（`env_layer_checker` 在两语料里都是主力 checker，GitHub 侧环境层占 35.8% 且更高），RQ1 的跨语料对比结论（Finding 3）需要重跑后才能确认。

---

## 6. 建议的修复优先级

| 优先级 | 动作 | 影响面 |
|---|---|---|
| P0 | 删除或重写 `env_constraint_checker`（合成证据 + 层级错标） | 14 条全废，且污染环境层计数 |
| P0 | `url_validator` 只校验真实网络调用并重放参数，跳过命名空间/占位符 | 7 条全废 |
| P0 | `dependency_version_drift` 需"契约声明了版本"才触发，并核对镜像实际版本 | 16 条中 15 条废 |
| P1 | 环境层判定绑定 Dockerfile/task.md 实际环境，禁止假设场景 | 环境层存活率 27%→可望翻倍 |
| P1 | 引文反查行号并回写；找不到引文的 finding 直接丢弃 | 20 条硬错误 + 112 条行号漂移 |
| P1 | 按 `root_cause_id` 合并重复 finding | 26 条重复 |
| P2 | 加层级决策树（先判两端制品类型，再判层级） | 40 条误标 |
| P2 | `not_a_contract` 类：把"给 Agent 的方法学指引"与"对能力的承诺"区分开 | 27 条口径类 |

---

## 7. 口径与局限

1. **复核者的严格口径**：本轮判定要求矛盾"可证实（demonstrable）"。因此像"文档承诺通用支持、代码只支持合规输入，但随附输入恰好合规"这类 finding 被判为 `speculation`。如果你采用更宽的口径（"承诺在一般情况下不成立即可"），存活率上限为 50.1%（160 + 29 条 speculation）。
2. **两轮独立运行的差异**：第一次运行 confirmed/mislabeled/invalid = 138/36/203，第二次 = 120/40/217（第二轮 100% 维持了第一轮的标记）。invalid 稳定在 **54–58%**，confirmed 稳定在 **32–37%**。差异约 ±5%，来自判定的边缘案例。
3. **对抗裁定未推翻任何一条**：说明第一轮判定本身偏保守；但也意味着第二轮没有独立提供"反向纠错"能力，建议由人工抽查 `speculation` 与 `not_a_contract` 两类（共 56 条）后再定稿。
4. **`mislabeled` 的处理建议**：这 40 条是真问题、错标签。如果重跑审计，它们应当以修正后的标签重新入库，而不是丢弃。
5. 本次只复核了 **SkillBench**。GitHub 侧 488 个 skill、1022 条 finding 尚未复核，而两者共用同一套 checker——按 §3 的 checker 存活率，GitHub 侧预计同样有 40–55% 会被否。

---

## 8. 产物清单

```
paper_audit_reports/skillbench_verification/
├── verify_evidence.py            第一层：引文与磁盘文件的逐字核对
├── build_verify_input.py         组装复核输入（含真实文件上下文）
├── aggregate_verification.py     汇总 + 计算对 RQ1 的影响
└── outputs/
    ├── evidence_integrity.csv          746 条引文的核对结果
    ├── verify_input.json               377 条 finding 的复核输入
    ├── verdicts/pass1_*.json           第一轮判定（19 批）
    ├── verdicts/pass2_*.json           第二轮对抗裁定（13 批）
    ├── verification_results.csv        ★ 逐 finding 最终判定 + 理由 + 修正标签
    ├── verification_summary.md         ★ 汇总表（本文档的数据来源）
    └── verification_stats.json         结构化统计
```

`verification_results.csv` 是最重要的产物：每条 finding 都有 `verdict`、`reason_code`、`reason`（复核者的具体理由，含被引文件与行号）、`final_l1/l2/l3`（修正后的标签），可直接用于重跑审计或人工抽查。

---

## 附：论文可用段落（English, paper-ready）

### 版本 A —— 与实际情况一致（全量复核，非抽样）

> **Exhaustive re-validation of the SkillBench findings.** To verify that the automated audit is
> reliable, we re-examined every one of the 377 SkillBench findings rather than a sample. Each
> finding was re-judged independently against the taxonomy definition by a verifier given access to
> the quoted artifacts on disk, and every finding that was not confirmed was then re-adjudicated by
> a second adversarial reviewer instructed to overturn unsound flags [52]. Of the 377 findings,
> 120 (31.8%) were confirmed with their original label and 40 (10.6%) were judged genuine but
> mislabelled; 160 (42.4%) therefore satisfy our contract-inconsistency definition, while 217
> (57.6%) were rejected — most often because the two quoted artifacts do not actually conflict
> (113), because the conflict holds only under a hypothetical environment (29), or because the
> quoted text states a methodological instruction rather than a capability promise (27). Two
> independent runs of the re-judgement produced rejection rates of 53.8% and 57.6%, and the
> adjudication pass overturned none of the first pass's flags. All SkillBench results in this paper
> are computed on this verified subset.
>
> Independently of the semantic judgement, a mechanical check of all 746 quoted evidence spans
> found 506 (67.8%) matching the cited lines verbatim, 112 whose line numbers had drifted, and 20
> (2.7%) that could not be located in the cited file at all. Two of the seven checkers produced no
> surviving finding (0/14 and 0/7), and the rejection rate was strongly checker-dependent,
> ranging from 0% to 57.1%.

### 版本 B —— 若再补一次人工抽样复核（模板同构，需填数字）

> **Manual validation of the verified candidates.** To verify that the automated re-judgement is
> reliable, two authors independently reviewed a random sample of `N` findings drawn from the 377
> SkillBench findings, with a third resolving disagreements [52]. Of the `N` findings, `X` (`Y`%)
> were judged genuinely contract-inconsistent with `Z`% inter-rater agreement (Cohen's
> $\kappa$ = `K`) [10], confirming that the automated re-judgement aligns well with human judgment.

建议的抽样设计（若要做版本 B）：

- **抽样框**：377 条全量；按判定分层抽样（confirmed / mislabeled / invalid 各抽一部分），
  否则 57.6% 的 invalid 会主导样本、κ 被高估。
- **最小样本量**：每层 40 条以上（合计约 120 条）才能把 κ 的 95% 置信区间压到 ±0.15 以内。
- **一致性统计**：报 Cohen's κ（两位作者），并单独报 `speculation` / `not_a_contract` 这 56 条
  的 κ——它们是最可能出现分歧的口径类判定，也是你决定"严/宽口径"的依据。
- **分歧处理**：第三位作者裁决，并记录分歧原因（写进 Threats to Validity 比只报一个 κ 更有说服力）。
