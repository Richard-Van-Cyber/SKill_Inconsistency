# Skill 不一致性的轨迹级因果审计（Top 30）

> 上一轮（`skill_inconsistency_impact_top30.md`）只做到**曝光度**：finding 有没有进入 agent 的上下文。
> 本报告补上**因果**：读了 199 条执行轨迹，判断一条不一致性是否真的被踩到、agent 因此做了什么、
> 最终是拉低了成功率还是只多烧了 token / 时间。

- **轨迹来源**：`hf_downloads/submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3`
- **规模**：199 次运行 / 68 个任务 / 6,133 个工具调用轮次 / 505 次工具报错
- **脚本**：`analysis_tools/trace_forensics.py`（事件流重建 + 错误↔finding 匹配）、`analysis_tools/trace_causal_report.py`（判决）
- **产物**：`skill_trace_causal_audit.csv`（68 个任务的逐项指标）

---

## 0. 结论摘要

1. **整个 68 任务语料里，只有 5 个任务出现过「skill 自己的代码在 agent 面前抛异常」**（判据：报错文本里出现 `/skills/<skill>/...` 路径）。Top 30 里只有 3 个。
2. **Top 30 中只有 6 个任务的报错能与审计 finding 的文本对上**（STRONG 3 个、MEDIUM 5 个）。其余 22 个任务在轨迹里找不到任何指向该 finding 的因果链。
3. **真正「effectiveness 下降 + 轨迹确证 + 归因到审计 finding」的只有 1 个任务：`latex-formula-extraction`。**它的 F-001（文档写 timeout=600、实现是 120）在轨迹里被直接观测到：agent 先按默认值跑，`timed out after 120s`；照文档显式传 `--timeout 600`，`timed out after 600s`；3/3 运行失败，43% 的轮次花在恢复上。
4. **efficiency 下降但任务仍通过的有 4 个**：`sec-financial-report`（STRONG，3/3 通过但每次都踩 `FileNotFoundError: /root/INFOTABLE.tsv`）、`dapt-intrusion-detection`（STRONG，3/3 通过但 skill 的 `pcap_utils.py` 抛 `TypeError: unsupported operand type(s) for -: 'Ether' and 'Ether'`）、`exceltable-in-ppt`（`No module named markitdown`）、`earthquake-plate-calculation`。
5. **Top 30 里有 11 个任务在 ≥2/3 的运行中 agent 完全绕开了 skill（自己写实现）**，skill 只被加载、读了 SKILL.md 就被丢在一边。这些任务的 IIS 排名是虚高的。
6. **审计漏报被轨迹抓到**：`dapt-intrusion-detection` 的真实崩溃点（scapy `Ether` 相减）不在该任务的任何 finding 里；另外两个 skill 代码崩溃的任务 `court-form-filling`、`protein-expression-analysis` 的审计报告恰好是那 29 份失效报告之一。

---

## 1. 方法

对每条轨迹做四件事：

1. **事件流重建**：按顺序抽出每个 `tool_use`（`Skill` / `Read` / `Write` / `Bash`）与每个 `tool_result`，
   用 `is_error`、`Traceback (most recent call last)`、`Exit code [1-9]`、`<tool_use_error>` 判定报错。
2. **错误 ↔ finding 匹配（两级）**：
   - **STRONG**：报错的 traceback 路径里出现 `/skills/<该 finding 所在子技能>/`，即 **skill 自己的代码**在跑的时候炸了。
   - **MEDIUM**：报错文本里出现了**逐字出现在该 finding 证据（`evidence.source_a/b.span_text`）里**的标识符。
3. **特异性过滤**：第一版匹配用的是「rationale 里的词」，一次跑出 37 个 run 的假阳性（`python`、`command`、
   `directory`、`analysis`、`solution` 这类词都会命中）。现在只接受「含 `_`、含内部大写、或属于已知包/工具名」的标识符，
   并配一份通用词黑名单；命中数从 37 个 run 降到 16 个 run，剩下的每一条都人工核对过。
4. **恢复开销**：对每个报错轮次，数到下一个成功工具结果之间的轮次数，累加得到 `recovery_turns`；
   用 `recovery_turns / turns` 表示「被错误—修复循环吃掉的轮次占比」。

> 需要说清楚的口径：**STRONG 只证明「skill 的某个文件在运行时炸了」，不自动证明炸的就是审计那条 finding。**
> 例如 `dapt-intrusion-detection` 的 STRONG 命中来自 `pcap-analysis/pcap_utils.py`，但异常内容是 scapy 类型错误，
> 而审计查的是该文件里的硬编码路径问题 —— 所以它算「skill 代码缺陷确证、但审计条目未覆盖」。

---

## 2. 全局读数

| 指标 | 数值 |
|---|---|
| 轨迹条数 | 199 |
| 工具调用轮次 | 6133 |
| 工具报错次数 | 505（占轮次 8.2%） |
| 加载过至少一个 skill 的运行 | 151 / 199 |
| 自己写了实现脚本（绕过 skill）的运行 | 85 / 199 |

### 2.1 skill 自己的代码在运行时崩溃的任务（全语料只有 5 个）

| Task | 崩溃运行数 | 报错内容 | 该任务 Top30 排名 |
|---|---|---|---|
| `latex-formula-extraction` | 2/3 | marker: raise TimeoutError(f"marker_single timed out after {timeout}s") from exc || marker: raise TimeoutError(f"marker_ | #15 |
| `sec-financial-report` | 3/3 | 13f-analyzer: FileNotFoundError: [Errno 2] No such file or directory: '/root/INFOTABLE.tsv' || 13f-analyzer: FileNotFoun | #29 |
| `court-form-filling` | 2/3 | pdf: FileNotFoundError: [Errno 2] No such file or directory: '/tmp/pdf_images/page_1.png' || pdf: FileNotFoundError: [Er | Top30 之外 |
| `dapt-intrusion-detection` | 2/3 | pcap-analysis: TypeError: unsupported operand type(s) for -: 'Ether' and 'Ether' || pcap-analysis: TypeError: unsupporte | Top30 之外 |
| `protein-expression-analysis` | 1/3 | xlsx: FileNotFoundError: [Errno 2] No such file or directory: '/logs/agent/sessions/skills/xlsx/protein_expression.xlsx' | Top30 之外 |

`court-form-filling` 与 `protein-expression-analysis` 是那 29 份 comprehension 失效报告里的任务 ——
**它们的 skill 代码真的会崩，但审计报告写的是「0 findings」**。这是「0 finding ≠ 干净」最直接的证据。

---

## 3. 确认的因果链逐条

### 3.1 `latex-formula-extraction` —— 唯一一例 effectiveness + efficiency 双降（审计 finding 被轨迹确证）

| 项 | 内容 |
|---|---|
| 审计 finding | F-001（high）：`marker/SKILL.md` 把 `pdf_to_markdown` 的 `timeout` 默认值写成 **600**，实现 `marker/scripts/marker_to_markdown.py` 里是 **120** |
| 轨迹证据 | 该 skill 自己的脚本在 36 处出现在 agent 的执行里；真正执行到 `marker_to_markdown.py` 时抛 `TimeoutError: marker_single timed out after 120s` |
| 关键观测 | `timed out after 120s` 出现 **4 次**，`timed out after 600s` 出现 **2 次** —— agent 先按文档以为默认是 600，结果是 120 超时；随后照文档显式传 `--timeout 600`，又超时 |
| 后果 | 3/3 运行 reward=0；24 次报错 / 88 轮次；**43% 的轮次花在错误—修复循环上**（Top 30 最高） |

三次运行的命令序列（`python` → `python3` → 显式传参，逐次退让）：

```
latex-formula-extraction__paper-v1-uinQUtd-0001
  cd /logs/agent/sessions/skills/marker && python  scripts/marker_to_markdown.py /root/latex_paper.pdf
  cd /logs/agent/sessions/skills/marker && python3 scripts/marker_to_markdown.py /root/latex_paper.pdf
  cd /logs/agent/sessions/skills/marker && python3 scripts/marker_to_markdown.py /root/latex_paper.pdf --timeout 600
latex-formula-extraction__paper-v1-4sJ3VPF-0002
  ... 最后放弃 skill，直接 timeout 120 marker_single /root/latex_paper.pdf --disable_image_extraction
```

这是本批数据里**唯一一条「审计 finding 文本 → 实现行为 → 运行失败」完整闭环**的证据。

### 3.2 `sec-financial-report` —— 只有 efficiency 下降，任务照样通过

| 项 | 内容 |
|---|---|
| 审计 finding | F-002（high）：`13f-analyzer/scripts/holding_analysis.py` 直接读根目录 `INFOTABLE.tsv`，忽略 `--quarter`；而 `one_fund_analysis.py` 假定按季度分目录 —— 两个脚本对数据目录布局的环境假设互相矛盾 |
| 轨迹证据 | **3/3 运行**都命中：`FileNotFoundError: [Errno 2] No such file or directory: '/root/INFOTABLE.tsv'`，traceback 起点就是 `/logs/agent/sessions/skills/13f-analyzer/scripts/holding_analysis.py:38` |
| 后果 | 3/3 **全部通过**（reward=1.0），但 88 轮次里 8 次报错、7 个轮次用于恢复 |

这个任务在上一轮排名里是 **#20「潜在风险」档**（S/T/W 全 0）。轨迹审计把它上修：
**不一致性确实每次都被踩到，只是 agent 有能力绕过去，所以只损失效率、不损失效果。**

### 3.3 `dapt-intrusion-detection` —— skill 代码确证崩溃，但审计没查到这一条

| 项 | 内容 |
|---|---|
| 审计 findings | F-001/F-002/F-003 都是「硬编码绝对路径 `/root/skills/pcap-analysis`」类问题 |
| 真实崩溃点 | `/logs/agent/sessions/skills/pcap-analysis/pcap_utils.py` 抛 `TypeError: unsupported operand type(s) for -: 'Ether' and 'Ether'`（scapy 版本/API 漂移） |
| 后果 | 2/3 运行命中；3/3 **全部通过**；37 轮次、3 次报错 |

结论有两层：**(a)** 该 skill 的代码确实会崩；**(b)** 崩溃的原因**不在审计报告里** —— 这是 `skill-audit` 的一处漏报，
与上一轮记录的「检测器对 5 条轨迹证据命中 0 条」是同一类问题。

### 3.4 `pddl-tpp-planning` —— MEDIUM 级，但 3/3 运行都中

| 项 | 内容 |
|---|---|
| 审计 finding | F-001/F-003/F-013：SKILL.md 演示 `from unified_planning.shortcuts import SequentialPlanValidator` 等 API |
| 轨迹证据 | **3/3 运行**：`ImportError: cannot import name 'SequentialPlanValidator' from 'unified_planning.shortcuts'`（全语料共 6 次）+ `AttributeError: module 'unified_planning' has no attribute ...` |
| 后果 | 3/3 失败；14 次报错 / 75 轮次；21% 轮次用于恢复 |

判为 MEDIUM 而不是 STRONG 的原因：报错发生在 **agent 自己写的 `/app/solve_tpp.py`** 里，
不是 skill 目录下的文件。但那个 import 语句逐字来自 SKILL.md 的示例段落 —— 属于「文档错误传播到 agent 代码」。
3/3 运行还都同时满足「加载了 skill 但自己写实现」，所以 skill 的贡献是**误导性的文档**，不是可复用的代码。

### 3.5 其余 MEDIUM 命中

| Task | 命中运行 | 证据 | 后果 |
|---|---|---|---|
| `setup-fuzzing-py` | 2/3 | `import atheris` 失败（F-001：文档声明的 Setup 参数列表与自身示例不符） | 0% 通过，644 轮次 |
| `exceltable-in-ppt` | 1/3 | `/usr/bin/python3: No module named markitdown`（F-001：SKILL.md 的依赖清单没包含实际必须的包） | 100% 通过，纯效率损失 |
| `earthquake-plate-calculation` | 1/3 | `eq["longitude"]` KeyError / `Point` / `PlateName` 字段名冲突（F-005） | 1/3 失败 |
| `r2r-mpc-control` | 1/3 | `num_sections` 变量在子技能间未定义（F-005） | 0% 通过 |

---

## 4. Top 30 的轨迹判决表

`ST` = 有 skill 自身代码出现在 traceback 的运行数；`MD` = 报错命中 finding 证据标识符的运行数；
`绕过` = agent 自己写实现而不调用 skill 的运行数；`恢复%` = 被错误—修复循环吃掉的轮次占比。

| # | Task | IIS | 通过率 | 轮次 | 报错 | 恢复% | skill代码崩 | ST | MD | 绕过 | 轨迹判决 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `pddl-tpp-planning` | 83.7 | 0% | 75 | 14 | 21% | 0 | 0 | 3 | 3/3 | **effectiveness 下降（MEDIUM）** |
| 2 | `offer-letter-generator` | 68.1 | 33% | 16 | 4 | 25% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 3 | `manufacturing-fjsp-optimization` | 52.1 | 67% | 202 | 12 | 6% | 0 | 0 | 0 | 3/3 | **skill 被绕过，无因果机会** |
| 4 | `travel-planning` | 44.0 | 33% | 62 | 3 | 5% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 5 | `suricata-custom-exfil` | 42.5 | 0% | 156 | 6 | 4% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 6 | `r2r-mpc-control` | 42.1 | 0% | 158 | 9 | 6% | 0 | 0 | 1 | 3/3 | **effectiveness 下降（MEDIUM）** |
| 7 | `data-to-d3` | 41.8 | 0% | 68 | 2 | 3% | 0 | 0 | 0 | 3/3 | **skill 被绕过，无因果机会** |
| 8 | `weighted-gdp-calc` | 41.5 | 67% | 84 | 7 | 12% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 9 | `earthquake-plate-calculation` | 40.7 | 67% | 32 | 4 | 12% | 0 | 0 | 1 | 1/3 | **仅 efficiency 下降（MEDIUM）** |
| 10 | `reserves-at-risk-calc` | 34.9 | 0% | 128 | 9 | 7% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 11 | `organize-messy-files` | 34.7 | 0% | 66 | 2 | 3% | 0 | 0 | 0 | 1/3 | **仅曝光，无因果证据** |
| 12 | `paper-anonymizer` | 34.1 | 0% | 11 | 2 | 18% | 0 | 0 | 0 | 1/3 | **仅曝光，无因果证据** |
| 13 | `lab-unit-harmonization` | 34.0 | 33% | 56 | 3 | 7% | 0 | 0 | 0 | 3/3 | **skill 被绕过，无因果机会** |
| 14 | `shock-analysis-supply` | 33.6 | 0% | 324 | 33 | 10% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 15 | `latex-formula-extraction` | 31.9 | 0% | 88 | 24 | 43% | 2 | 2 | 0 | 0/3 | **effectiveness+efficiency 双降（STRONG）** |
| 16 | `lake-warming-attribution` | 31.4 | 67% | 47 | 3 | 6% | 0 | 0 | 0 | 1/3 | **仅曝光，无因果证据** |
| 17 | `azure-bgp-oscillation-route-leak` | 31.1 | 0% | 44 | 3 | 7% | 0 | 0 | 0 | 2/3 | **skill 被绕过，无因果机会** |
| 18 | `citation-check` | 30.0 | 100% | 93 | 0 | 0% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 19 | `hvac-control` | 27.6 | 0% | 72 | 1 | 1% | 0 | 0 | 0 | 3/3 | **skill 被绕过，无因果机会** |
| 20 | `dynamic-object-aware-egomotion` | 26.6 | 0% | 62 | 14 | 31% | 0 | 0 | 0 | 3/3 | **skill 被绕过，无因果机会** |
| 21 | `glm-lake-mendota` | 25.7 | 100% | 83 | 3 | 4% | 0 | 0 | 0 | 2/3 | **skill 被绕过，无因果机会** |
| 22 | `shock-analysis-demand` | 25.7 | 0% | 68 | 3 | 4% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 23 | `multilingual-video-dubbing` | 24.3 | 0% | 84 | 9 | 10% | 0 | 0 | 1 | 3/3 | **effectiveness 下降（MEDIUM）** |
| 24 | `mario-coin-counting` | 21.7 | 67% | 41 | 1 | 2% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 25 | `pptx-reference-formatting` | 21.6 | 0% | 84 | 11 | 19% | 0 | 0 | 0 | 2/3 | **skill 被绕过，无因果机会** |
| 26 | `flood-risk-analysis` | 21.2 | 100% | 29 | 1 | 3% | 0 | 0 | 0 | 1/3 | **仅曝光，无因果证据** |
| 27 | `civ6-adjacency-optimizer` | 19.1 | 67% | 73 | 6 | 10% | 0 | 0 | 0 | 0/3 | **仅曝光，无因果证据** |
| 28 | `grid-dispatch-operator` | 18.5 | 33% | 52 | 9 | 21% | 0 | 0 | 0 | 1/3 | **仅曝光，无因果证据** |
| 29 | `sec-financial-report` | 17.7 | 100% | 88 | 8 | 8% | 3 | 3 | 3 | 0/3 | **仅 efficiency 下降（STRONG）** |
| 30 | `3d-scan-calc` | 17.5 | 100% | 16 | 0 | 0% | 0 | 0 | 0 | 1/3 | **仅曝光，无因果证据** |

---

## 5. 为什么多数高排名任务其实没有因果

### 5.1 被绕过（≥2/3 的运行里 agent 自己写实现，skill 代码没被调用）

Top 30 里有 11 个任务满足「≥2/3 的运行里 agent 自己写了实现脚本」。
典型序列是：`Skill(pddl-skills)` → 读 SKILL.md → **不调用 skill 的脚本** → 自己 `Write /app/solve_tpp.py`。
此时 skill 对结果的唯一影响是它的文档内容（可能误导），它的代码、数据结构、校验逻辑从未被使用。

| Task | 绕过运行 | 观测通过率 |
|---|---|---|
| `pddl-tpp-planning` | 3/3 | 0% |
| `manufacturing-fjsp-optimization` | 3/3 | 67% |
| `r2r-mpc-control` | 3/3 | 0% |
| `data-to-d3` | 3/3 | 0% |
| `lab-unit-harmonization` | 3/3 | 33% |
| `hvac-control` | 3/3 | 0% |
| `dynamic-object-aware-egomotion` | 3/3 | 0% |
| `multilingual-video-dubbing` | 3/3 | 0% |
| `azure-bgp-oscillation-route-leak` | 2/3 | 0% |
| `glm-lake-mendota` | 2/3 | 100% |
| `pptx-reference-formatting` | 2/3 | 0% |

### 5.2 仅曝光、无因果证据

| Task | IIS | 报错次数 | 通过率 |
|---|---|---|---|
| `offer-letter-generator` | 68.1 | 4 | 33% |
| `travel-planning` | 44.0 | 3 | 33% |
| `suricata-custom-exfil` | 42.5 | 6 | 0% |
| `weighted-gdp-calc` | 41.5 | 7 | 67% |
| `reserves-at-risk-calc` | 34.9 | 9 | 0% |
| `organize-messy-files` | 34.7 | 2 | 0% |
| `paper-anonymizer` | 34.1 | 2 | 0% |
| `shock-analysis-supply` | 33.6 | 33 | 0% |
| `lake-warming-attribution` | 31.4 | 3 | 67% |
| `citation-check` | 30.0 | 0 | 100% |
| `shock-analysis-demand` | 25.7 | 3 | 0% |
| `mario-coin-counting` | 21.7 | 1 | 67% |
| `flood-risk-analysis` | 21.2 | 1 | 100% |
| `civ6-adjacency-optimizer` | 19.1 | 6 | 67% |
| `grid-dispatch-operator` | 18.5 | 9 | 33% |
| `3d-scan-calc` | 17.5 | 0 | 100% |

其中 `citation-check`（IIS 30.0，上一轮 #12）和 `3d-scan-calc`（#21）**零报错、100% 通过**。
它们的排名完全来自 `Gate × 0.30` 这一潜在风险常数项 —— 轨迹审计确认：**在这批运行里它们没有造成任何损失。**

---

## 6. 对上一轮 Top 30 排名的修正

| 分类 | 任务 | 处理建议 |
|---|---|---|
| **A. 轨迹确证，且损失 effectiveness** | `latex-formula-extraction`（STRONG，F-001 闭环）、`pddl-tpp-planning`（MEDIUM，3/3 中）、`setup-fuzzing-py`、`r2r-mpc-control` | 优先修，且修完可预期效果提升 |
| **B. 轨迹确证，仅损失 efficiency** | `sec-financial-report`（STRONG，3/3 中）、`dapt-intrusion-detection`（STRONG）、`exceltable-in-ppt`、`earthquake-plate-calculation` | 值得修（省 token/时间），但别期望成功率上涨 |
| **C. 曝光但无因果证据** | `citation-check`、`flood-risk-analysis`、`3d-scan-calc`、`sales-pivot-analysis`、`mario-coin-counting`、`civ6-adjacency-optimizer`、`offer-letter-generator`、`suricata-custom-exfil`、`lake-warming-attribution`、`organize-messy-files`、`pdf-excel-diff`、`xlsx-recover-data` | 降级为待观察 |
| **D. 被绕过** | `manufacturing-fjsp-optimization`、`lab-unit-harmonization`、`hvac-control`、`dynamic-object-aware-egomotion`、`pptx-reference-formatting`、`mars-clouds-clustering`、`threejs-to-obj`、`azure-bgp-oscillation-route-leak`、`jpg-ocr-stat`、`glm-lake-mendota` | 先解决「skill 为什么不被用」，再谈修不一致性 |

**最关键的一条修正**：上一轮排名第 1 的 `pddl-tpp-planning`（IIS 83.7）在轨迹里确实 3/3 中招，
但它中招的方式是「照抄 SKILL.md 的 import 示例 → ImportError」，而 skill 的可执行代码从未被调用。
修这条不一致性（把示例改成实际可用的 API）预计有正收益；但把它排在「skill 质量」第一名的位置上，
掩盖了真实问题：**这个 skill 的采用率为 0/3**。

---

## 7. 局限

1. **匹配是文本级的，不是语义级的。** STRONG 只说明 skill 文件出现在 traceback 里；
   MEDIUM 只说明报错提到了 finding 证据里的某个标识符。两者都可能误报，也可能漏报需要跨轮次推理的因果。
2. **没有 rerun 对照。** 要断言「修掉 F-001 后 latex-formula-extraction 会通过」，需要把该 skill 修好后在同一 harness 下重跑 3 次，而不是靠轨迹推断。
3. **样本量极小。** 大多数任务只有 3 次运行，`0/3 失败` 与 `1/3 失败` 之间的差异不具统计意义。
4. **语料与当前仓库版本不完全一致。** 轨迹是 paper-v1 归档（2026-01），审计报告生成于 2026-09-23；少数任务在两版之间改过名，轨迹里出现的 skill 名可能与当前目录名不同。
5. **只覆盖 68/87 个任务**，29 份失效报告对应的任务里没有一个能参与本报告的排序。
