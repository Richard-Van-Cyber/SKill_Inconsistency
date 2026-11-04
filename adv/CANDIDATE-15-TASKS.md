# 追加 15 个 task 的选型建议（在动态运行中验证不一致性的影响）

日期：2026-09-25
数据源：`hf_downloads/submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3`
（**199 条轨迹 / 68 个 task**，with-skills 臂，claude-haiku-4-5，每 task 约 3 trial）

工具：`analysis_tools/skillsbench_traj_mine.py`（产出 `/tmp/skillsbench_traj_mining.json`）

---

## 0. 为什么这个数据集适合回答你的问题

1. **它是 with-skills 臂**，与我的 `OriginalSkill` 臂同构，且**每次 `Skill` 调用会把完整 SKILL.md 注入轨迹**
   （轨迹里能看到 `Base directory for this skill: ...` 后紧跟全文）。所以"文档写了什么"与"模型随后撞到什么"可以直接对齐。
2. **199 条轨迹带 reward、timing、逐条 tool_result 的 `is_error`**，可以量化"不一致性在运行中的代价"。
3. 68 个 task **全部**都在我的 87 份 `audit_report.json` 覆盖范围内 → 轨迹证据与审计发现可以交叉。

---

## 1. 选型判据（来自我自己那轮实验的教训，不是拍脑袋）

| 判据 | 为什么 | 我的依据 |
|---|---|---|
| **T：轨迹已证代价** | 只有真报过错/烧过轮次的不一致性才值得修 | P12：审计取证 ≠ 轨迹取证 |
| **B：绑定约束** | 若模型 2/3 的运行自行绕开了，修了也没用 | P10；ACC 案例 L3 ✗ |
| **S：可解**（reward > 0 或 P11 闸门通过） | 无解任务上解除阻塞**只换来 token**，换不来分数 | 我的 civ6/grid 实测：依赖命令 6→1，token 431k→1038k，分数仍 0 |
| **A：审计有发现** | 你定义的 inconsistency 体系里确实记了一笔 | 否则无法把"影响"归到某个类别 |
| **D：类型分散** | 15 个都测同一种缺陷没有信息量 | 覆盖 environmental / document / implementation 三层 |

**关键取舍**：优先选**可解**的 task。我上一轮的结论是——不一致性只有在任务本来有解时才会兑现成分数；
无解任务上它只兑现成成本。所以 C 组（0 分但 P11 已验证）用于**测过程代价**，A/B 组用于**测分数影响**。

---

## 2. 推荐的 15 个 task

### A 组：环境类不一致，轨迹已证代价，且**可解**（6 个）

| # | task | reward | findings | 轨迹里的靶向报错 | 文档侧证据（doc-induced） |
|---|---|---|---|---|---|
| 1 | **`weighted-gdp-calc`** | 0.67 | **12**（5 env / 3 over / 2 shared / 2 iface） | `No module named pandas` ×3、`pep668` ×2 | 文档 4 处 `python recalc.py` + `import pandas` |
| 2 | **`exceltable-in-ppt`** | **1.00** | 5（4 env / 1 external） | `python: command not found` ×3、`unzip`、`file` | 文档 **34 处**裸 `python`（`xlsx`/`pptx` skill） |
| 3 | **`powerlifting-coef-calc`** | **1.00** | 1（env） | `pandas` ×3、`pep668` ×2、`python` ×1 | 文档 **13 处**裸 `python` |
| 4 | **`protein-expression-analysis`** | **1.00** | 2（shared / env） | `pandas` ×3 | 文档裸 `python` + `import pandas` |
| 5 | **`glm-lake-mendota`** | **1.00** | **12**（4 env / 4 over / 2 semantic / 2 iface） | `eisdir`、`python` | 容器成本也高：1073s / 1331k tok |
| 6 | **`earthquake-plate-calculation`** | 0.67 | 9（4 over / 3 env / **1 dependency_version_drift** / 1 service） | `file_too_big`、`eisdir` | 含唯一一条 `dependency_version_drift`，类型稀缺 |

### B 组：文档层 / 实现层不一致，可解（5 个）

| # | task | reward | findings 构成 | 轨迹代价 |
|---|---|---|---|---|
| 7 | **`spring-boot-jakarta-migration`** | 0.33 | 12：4 `shared_concept_definition_conflict` + 2 `semantic_conflict` + 1 `cross_document_process_conflict` + 5 `over_promised` | 4 条 err result，979k tok |
| 8 | **`manufacturing-fjsp-optimization`** | 0.67 | 6：3 `over_promised` + 1 `interface_contract_mismatch` + 1 `shared_concept` + 1 env | **12 条 err result**，5860k tok / 405s |
| 9 | **`citation-check`** | **1.00** | 12：**11 `over_promised`（8 条 high）** + 1 external | 文档 **149 处**裸 `python`（`citation-management`） |
| 10 | **`sec-financial-report`** | **1.00** | 4：2 `over_promised` + 2 env | 8 条 err result：`no_such_file` ×4、traceback ×4 |
| 11 | **`lab-unit-harmonization`** | 0.51 | 3：`over_promised`（1 high） | `file_too_big`，2241k tok |

### C 组：当前 0 分，但**P11 闸门已验证 oracle 满分**（2 个）

用于回答"不一致性是否只是没被触发，而不是不存在"。

| # | task | findings | 备注 |
|---|---|---|---|
| 12 | **`r2r-mpc-control`** | **10**，四层全占（4 over / 2 env / 2 iface / 1 shared / 1 dependency_drift） | P11 已实测 oracle reward = 1.0 |
| 13 | **`hvac-control`** | 5：3 `environment_fact_conflict` + 2 `shared_concept` | P11 已实测 oracle reward = 1.0 |

### D 组：高成本疑难（2 个）

用于检验我上一轮的结论——**"解除阻塞只换来 token"**——在别的 task 上是否复现。

| # | task | reward | 证据 |
|---|---|---|---|
| 14 | **`energy-ac-optimal-power-flow`** | 0.00 | **全数据集最高成本：4722k tok / 721s**；`numpy/scipy/casadi` 缺失 + `pep668`；文档里有一条**裸 `pip install numpy==1.26.4 casadi==3.6.7`** |
| 15 | **`manufacturing-equipment-maintenance`** | 0.33 | **靶向缺陷最多（14）**：`file_too_big` ×5、`file` ×2、`pdftotext`、`fitz`/`PyPDF2`、`eisdir` ×2 |

---

## 3. 顺带发现的一条系统性缺陷（建议单独利用）

**26 / 68 个 task（38%）的 skill 文档里写着裸 `python`，而镜像里只有 `python3`。**

贡献来源是几个**共享 skill**：

| skill | 命中的 task 数 |
|---|---|
| `xlsx` | 24 |
| `pptx` | 24 |
| `senior-java` | 14 |
| `citation-management` | 13 |
| `pdf` | 10 |
| `senior-data-engineer` | 7 |
| `docx` | 5 |
| `pymatgen` | 4 |

这正是我 v2 修复里 **R2** 那一类，而且是**一处修改覆盖多个 task**（改 `xlsx` 的 SKILL.md 可同时影响 24 个 task）。
统计上的意义：**它天然构成一个"处理组 / 对照组"设计** —— 有裸 `python` 的 26 个 vs 没有的 42 个，
可以直接检验"文档缺陷 → 运行代价"的因果，而不需要我逐个构造对抗数据。

我已实测确认不是猜测：`court-form-filling` 镜像 `python: ABSENT`、`civ6` 镜像 `sqlite3: ABSENT`。

---

## 4. 建议的实验设计

对每个 task 跑三臂（复用我现有的 driver，配置不变）：

```
OriginalSkill     出厂 skill
RepairV2          只修轨迹已证的靶向缺陷（A/B 组）
NoSkill           对照
```

- **效果指标**：reward；以及"靶向报错计数"（这是我的教训：`command not found` 总量会被"模型跑得更久"污染，必须看靶向的）
- **效率指标**：未截断 cell 的 calls / seconds / tokens，**外加严格配对**
- **必测的两个子集**：① 两臂都得分 ② 分数持平 —— 我在 §上一轮发现这两档的结论不同（+6.9% vs +46k）

两个必须先做的前置：
1. **P11 可行性闸门**（`adv/feasibility_gate.sh`）—— 15 个里 C 组已验证，其余 13 个需要先跑；
2. **确认文档侧缺陷确实是 doc-induced** —— 我这次抽查就推翻了两个初判：
   - `lake-warming-attribution` 的 Dockerfile **已经装了 pandas/numpy/scipy**，它的真缺陷是 `Rscript` 缺失；
   - `travel-planning` 的 `No module named search_cities` 是**模型自己写的模块**，与文档无关，已剔除。

---

## 4b. 实际采用的最终 15 个（与上面的推荐有 2 处不同）

实施时因**镜像无法构建**替换了 2 个（两者的 Dockerfile 都从服务器访问不到的网络源拉东西）：

| 推荐 | 实际采用 | 原因 |
|---|---|---|
| `powerlifting-coef-calc` | **`flood-risk-analysis`** | 前者的 Dockerfile 从 github 下载 uv，服务器不可达 |
| `spring-boot-jakarta-migration` | **`offer-letter-generator`** | 前者的 Dockerfile 用 SDKMAN 装 Java，两次重试均 `curl (92) PROTOCOL_ERROR`；后者镜像已存在、findings 更多（12 vs 12）且分类更广（7 个 L2 vs 6 个）、并带一个经对抗协议验证过的修复 |

最终 15 个：citation-check、earthquake-plate-calculation、energy-ac-optimal-power-flow、exceltable-in-ppt、
flood-risk-analysis、glm-lake-mendota、hvac-control、lab-unit-harmonization、
manufacturing-equipment-maintenance、manufacturing-fjsp-optimization、offer-letter-generator、
protein-expression-analysis、r2r-mpc-control、sec-financial-report、weighted-gdp-calc。

---

## 5. 诚实说明：这批数据的一个限制

paper-v1 轨迹的**预算与我的实验不同**（例如 `setup-fuzzing-py` 单 task 11656k tok，是我 1M 上限的 11 倍），
且 `result.json` 里 `n_input_tokens` 等字段为 null，token 数是我从每条 message 的 `usage` **累加**得到的。
因此：

- 它的 reward **不能**直接和我的三臂数字并列；
- 它的用途是**筛选题 + 定位缺陷**（谁真的有代价），不是给出效果量。

选定后仍须在**我自己的同配置三臂**里重跑，才是可比的结论。
