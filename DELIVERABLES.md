# 交付清单：需求 → 产物 对照

每一项都是**已存在于仓库、可直接打开**的文件。路径相对于仓库根 `skillEvaluation/`。

---

## 1. 需求逐条对照

| 需求原文 | 产物 | 说明 |
|---|---|---|
| **25 个 task 在三种配置下的实验数据** | `experiments/multi25-20260925/dataset/cells.csv`（逐 cell 一行）<br>`cells.jsonl`（保留嵌套字段）<br>`manifest.json`（来源与计数） | 225 cell = 25 task × 3 臂 × 3 trial |
| **reward** | `cells.csv` 的 `score`，另有 `raw_reward` | `raw_reward` 用于验证器格式受限的 task（`glm-lake-mendota`） |
| **time** | `agent_seconds` / `total_wall_seconds` / `verifier_seconds` / `setup_seconds` | 四段分解 |
| **token** | `total_tokens` / `prompt_tokens` / `completion_tokens` / `cli_total_cost_usd` | 99% 是 prompt |
| **执行轨迹** | `cells.csv` 的 `trace` 字段 → `cli.stdout.jsonl` | 已校验 **165/165 可解析**，共 **91.8 MB**；含完整对话、每次 `Skill` 注入的 SKILL.md 全文、每条 Bash 命令与输出、`is_error` 标记 |
| **修复过程** | `experiments/multi25-20260925/analysis/REPAIR-v3-NOTES.md`（9 节）<br>`haiku45-threeway-20260917/REPAIR-DESIGN-v2.md`<br>`experiments/multi25-20260925/analysis/repair-v2-vs-v3.md` | 含判据、逐文件依据、**被排除的候选及理由**、原则 3 的轨迹复核 |
| **修复后的 skill** | `fixed_skills_v3/`（新 15 个 task）<br>`fixed_skills_v2/`（原 10 个 task） | 与出厂 skill 并排保留，可直接 diff |
| **整理数据集** | 同上 `dataset/` 五个文件 + `README.md`（字段含义、统计口径、溯源、已知限制） | |
| **effectiveness 与 efficiency 报告** | `experiments/multi25-20260925/dataset/summary.md`（7 节，自动生成）<br>`experiments/multi25-20260925/dataset/section4.md`（论文 §4 的 headline 数据块：ITT 口径、零编辑安慰剂对照、Fisher 检验、token 的轮次/每次调用分解）<br>`experiments/multi25-20260925/analysis/FINAL-REPORT.md`（论文面向，§4 由上面的文件自动注入） | summary.md 与 section4.md 每轮自动刷新 |

---

## 1b. 37 个 task × 2 个模型（haiku / deepseek-flash）的汇总

| 需求原文 | 产物 | 说明 |
|---|---|---|
| **37 个 task 在 deepseek 与 haiku 上的结果，按 effectiveness 与 efficiency 整理** | `experiments/MODEL-COMPARISON-37.md` | 7 节：数据与口径（含完整性核验）、effectiveness（scored-only / ITT、cell 加权与 task 等权配对、逐 task 配对 Δ、Fisher、**零编辑安慰剂对照**、模型主效应）、efficiency（每 run 中位数、截断率、选择效应与共同支持配对、同分对照、性价比）、**专题：deepseek 在两个语料上的对比**、逐 task 附录、限制、复现 |
| **统一后的逐 run 数据** | `experiments/model-comparison-37/cells.csv`（657 run = haiku 330 + deepseek 327）<br>`coverage.json`（覆盖/截断/来源）<br>`integrity.json`（对 run bundle 的核验） | 字段含 score/status/calls/turns/tokens/prompt/completion/agent+wall+verifier 秒/truncated/repair_edited |
| **可复现生成** | `experiments/build_37_comparison.py` | 一条命令重建上面四个文件；默认重跑 bundle 核验（657/657 `result.json` 的 score 与 status 全部一致） |
| **既有旁证** | `experiments/traces-37/`（haiku 全量轨迹 + README）<br>`experiments/deepseek-traces/`（deepseek 全量轨迹 + README）<br>`experiments/model-comparison.md`（英文并排简表）<br>`experiments/MODEL-COMPARISON-REPORT.md`（撤回"模型×修复交互"结论的说明）<br>`experiments/placebo_check.py` / `verify_traces_37.py` | 轨迹逐 cell 可查；`verify_traces_37.py` 全通过 |

---

## 1c. wildskills13：13 个新 task（第三批 wildskills）

在既有 12 个 wildskills task 之外，从 GitHub 社区 skill 语料里再选 13 个、用同一套 SkillsBench
六件套格式构建，并跑同样的三臂实验（`NoSkill` / `OriginalSkill` / `FixedSkill`，3 trial）。

| 需求 | 产物 | 说明 |
|---|---|---|
| **选材（可复核）** | `experiments/wildskills13-20260929/scan/scan_candidates.py`<br>`scan/build_shortlist.py`<br>`scan/W0-SUMMARY.md` / `scan/shortlist.csv` / `scan/findings.csv` | 488 个已审计 skill / 1022 条 finding → 112 条 stage-1 合格 → 93 个本地可建包 → 32 个候选（类型覆盖优先） |
| **可行性判定** | `experiments/wildskills13-20260929/TRIAGE.md` | 6 路并行 triage：11 BUILD / 5 MAYBE / 10 REJECT；顺带推翻 10 条审计 finding（含 2 条被标 high 的 PDF y 轴"缺陷"、2 条 `external_resource_invalid` 假阳性） |
| **13 个 task 包 + 覆盖层** | `wildskills/dynamic_eval/tasks/{graph-merge, financial-statements, skill-creator, todo-finder, understand-domain, agent-development, code-tour, pr-polisher, pdf-forms, cyq-analysis, dingtalk-todo, storybook-release, margin-analyzer}`（+ 额外 `filter-benchmark`）<br>`wildskills/dynamic_eval/fixed_skills/<同名>` | 每个包 = task.md / environment+Dockerfile / verifier（5–14 个检查项，ctrf+reward 契约）/ oracle / 修复覆盖层；**skill 不烤进镜像**，由 driver 按臂上传 |
| **登记表** | `experiments/wildskills13-20260929/tasks.json` | task → 源 skill → 缺陷类型 → 检查项 → 状态；论文 dataset 附录可直接引用 |
| **逐包闸门证据** | `experiments/wildskills13-20260929/gates/*-local.txt` | 每个 task 三段测量：oracle **全 1.0** / pristine 路径 0.0–0.71 / 空工作区 0.0；另有反绕过探针（手写产物、硬编码答案） |
| **构建规范** | `experiments/wildskills13-20260929/BUILD-GUIDE.md`<br>`scaffold_task.py` / `validate_tasks.py` / `check_deps.py` | 六件套规范、verifier 契约、G0/G1/G2/G4/G5 闸门、两阶段运行手册；两个预检工具在批内抓出 3 个真问题（缺 pypdf、pip 收到注释行、skill 目录重复） |
| **实验数据（运行中）** | `experiments/wildskills13-20260929/`（10 task / 90 cell）<br>`experiments/wildskills13b-20260929/`（3 task / 27 cell）<br>`experiments/wildskills13c-20260929/`（1 task / 9 cell，额外） | 主研究预算 60 req / 1M tok / 32k out，3 trial |
| **数据集与报告** | `experiments/wildskills13-20260929/consolidate13.py` → `experiments/wildskills13-dataset/{cells.csv,summary.md}`<br>`analyze_mechanism.py` → `mechanism.csv`（缺陷面/是否承重/错误签名）<br>`analyze_checks.py` → `checks.csv` + `checks.md`（逐检查项，把 reward 打开）<br>`REPORT.md`（论文面向：设计/任务清单/闸门/口径/结果/限制/复现）<br>`VERIFY-PRINCIPLES.md`（验证原理 × SkillsBench 原则逐条对照，含三处有意偏离与残余反作弊面）
<br>`REPAIR-PRINCIPLES.md`（修复流程 5 步 + 六条原则 + 方向实测分布，逐条带机械可复核证据）
<br>`TAXONOMY-MAPPING.md`（14 个 task ↔ 你的 3 L1 / 10 L2 分类的对应，每类的修复原则，以及按承重检查项复核后的真实覆盖率 7/10）<br>`finalize_when_done.sh`（等 driver 退出→回收→自动出全部产物） | 与既有 `wildskills-dataset/` 同 schema，可直接并排；`summary.md` 含 ITT 口径、**零编辑安慰剂噪声底**（`wildskills13-placebo-20260929`）与机制三节 |

---

## 2. 校验与机制（论文的方法学支撑）

| 产物 | 内容 |
|---|---|
| `analysis/verification-log.md` | **4a 修复清单终审 / 4b 注入内容端到端校验 / 4c 最高风险项定点核对** + 任务包完整性 + 跨 study 可比性 + P11 闸门（含闸门自身修掉的 3 个 bug）+ 环境事实实测 + 数据集完整性 |
| `analysis/mechanism-table.md` | 把 `command not found` / `No module named` 拆成 **doc-induced**（文档以命令形态点名）与模型即兴两类；已实测 `python` 失败只在 OriginalSkill 出现 6 次、RepairedSkill 为 0 |
| `analysis/FINAL-REPORT.md` | 研究问题、实验设计、修复方法学、结果表、**8 条已知限制**、复现命令 |

---

## 3. 可复现性

| 产物 | 用途 |
|---|---|
| `experiments/multi25-20260925/make_deliverables.sh` | **一条命令**产出全部论文产物（同步三个 study → 汇总 → 机制表 → 取证 → 完整性检查） |
| `analysis_tools/make_repair_v3.py` | 幂等重建 `fixed_skills_v3/`，自带完整性校验（文件集不变、非 `.md` 改动为 0） |
| `analysis_tools/consolidate25.py` | 生成 `dataset/`（含 `summary.md`） |
| `analysis_tools/section4.py` | 生成 `dataset/section4.md`（ITT、安慰剂对照、Fisher、token 分解），并原位注入 `FINAL-REPORT.md` 的 `AUTO-4` 标记之间；标记缺失时报错退出 |
| `analysis_tools/mechanism25.py` | 生成机制表 |
| `analysis_tools/multi25_forensics.py` | 对 OriginalSkill 轨迹做 doc-induced 判定 |
| `analysis_tools/classify_failures.py` | 区分**基础设施失败**（可重试）与**性能结果**（`agent_timeout` 保留）；含 `no_ctrf` 规则 |
| `analysis_tools/cli_availability.py` | 文档点名的 CLI 在镜像里是否存在 |
| `experiments/multi25-20260925/supervise.sh` / `phase3_watcher.sh` | 无人值守的 phase 1b / phase 3 派发 |
| `adv/feasibility_gate.sh` | P11 可行性闸门（已修 3 个假阴性 bug） |

---

## 4. 实验运行中产生的运维记录（供复现者参考）

| 事件 | 处置 |
|---|---|
| Docker 地址池耗尽（两次，共 27+36 cell 受影响） | driver 加**周期性清理**（每 2 次完成扫一次）；此后累计 `environment_error = 0` |
| API 额度耗尽（`剩余额度 -$0.055070`） | 充值后补跑 6 个 cell |
| 服务器整段掉线 | 未污染已完成数据 |
| 两个 task 镜像无法构建 | 替换（`powerlifting→flood-risk`、`spring-boot→offer-letter`） |
| `archive_artifacts` 的 `KeyError[task]` | 补全 15 个 task 的输出路径，并改为**安全默认值** |
| 本地副本过期（同步缺 `--delete`、只同步一个 study） | 均修复 |

---

## 5. 当前完成度

逐 task 的实时完成度见 `dataset/summary.md` §4（含缺失 cell 清单）。
判定标准：**25 个 task 每个都有 3 臂 × 3 trial = 9 个 cell**。
