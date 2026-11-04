# 对抗性样本总账：8 个构造 × 触发判定 × original/repaired 对比

**范围**：本轮工作共设计 **8 个对抗构造**（另有 1 个 mario 机械探针试点），
在 `10.0.0.64` 上实际跑了 **7 个配对实验、54 个 cell**（第 8 个在实验中途被叫停）。

**总判定**：

| 维度 | 结果 |
|---|---|
| 机制在**产出物层面**被真实触发 | **3 / 8**（02、04、07） |
| 其中触发**方向与预期一致**（original 受害、repair 规避） | **2 / 8**（04、07） |
| reward 层面出现**可归因于不一致性**的 original vs repaired 差异 | **0 / 7** |
| 由不一致性**确定导致校验失败**的 | **1 / 8**（04） |
| repair **反而制造失败**的 | **1 / 8**（02） |
| reward 有差异但**归因失败（混杂）** | **1 / 8**（06） |
| 完全未触发 | **3 / 8**（01、03、06 的运行侧） |

---

## 一、总表

`O` = OriginalSkill，`R` = RepairedSkill。reward 为 3 trial 均值。

| # | 任务 | 不一致性在哪 | 对抗设计 | cells | reward O → R | 触发？ | 判定依据 |
|---|---|---|---|---|---|---|---|
| 01 | earthquake-plate-calculation | `SKILL.md` 三套互斥选板字段名 | 数据：`PlateName`→`Name` | 12 | 出厂 0.667→**1.000**<br>对抗 1.000→0.667 | **✗** | 12 run **0 次 KeyError** |
| 02 | grid-dispatch-operator | 参考文档声明支持 MATPOWER Type-1；技能与**评分器都**忽略 MODEL 列 | 数据：缩放实例 + 共线 Type-1 重编码 | 12 | 出厂 0.667→**1.000**<br>type1 1.000→**0.333** | **✓（反向）** | 上报成本 3/3=200 vs 2/3≠200；修复**制造**了失败 |
| 03 | pddl-tpp-planning | `.skill` 实现用 `path.replace('.txt','.pkl')` 覆盖自身 | 数据：`plan_output` 扩展名 `.txt`→`.plan` | 12 | txt 1.000→0.667<br>plan 0.667→**1.000** | **✗** | 轨迹里 `pickle`/`.pkl` **0 次**；verifier 无解码错误 |
| **04** | **energy-unit-commitment** | **`SKILL.md` 可复制代码块：`alloc` 丢弃 `lb/ub/integer`** | **文档（无数据扰动）** | **6** | **0.000 → 0.000** | **✓ 且确定致败** | **6/6 照抄 helper；1/2 产出 report 有 36 个 commitment=2/3/4；verifier 点名 `123_STEAM_3`** |
| 05 | multilingual-video-dubbing | `SKILL.md` 可复制命令：`volume=0.5` 冒充峰值归一化 | — | 0 | — | 机制证明完成，**实验未跑** | 恒定 −6.02 dB，仅当源≈−17 LUFS 才合规 |
| 06 | sales-pivot-analysis | 同一索引 1 标为 ProductName / Quarter | 文档 | 6 | 0.333 → **1.000** | **✗ 归因失败** | 6/6 运行**从未用过** `pivotFields[1]`；真实自变量是文档可执行性（P8） |
| 07 | lab-unit-harmonization | 正文承诺 5% 钳制 / 代码块写死 `NO CLAMPING!` | 文档（出厂数据已有 423 个近边界值） | 6 | 0.604 → 0.465 | **✓ 但被淹没** | 钳制代码 **0/3 → 3/3**；近边界残留中位 **169 → 39**；但 reward 被 1–2 万个未换算值淹没（p=1.000） |
| 08 | adaptive-cruise-control | `SKILL.md` 可复制 `compute()` 无抗饱和，却在下一节宣称有三种方案 | 文档 | 3（中途叫停） | — | **仅机制证明** | 4 组增益下超调 **17–33%**（阈值 <5%）vs 有抗饱和 **0.2–0.6%**；实验被叫停无结果 |
| — | mario-coin-counting（试点） | 5 条 finding（`convert`/ffmpeg7/缺 cv2/dedup/依赖） | 机械探针 | 0 | — | **✗ 0/5** | 条件全为假；按 SKILL.md 参数跑 **8/8 帧**与 ground truth 一致 |

---

## 二、逐案：触发证据与 O/R 对比

### 01 · earthquake-plate-calculation —— **未触发**

数据扰动（`PlateName` → `Name`）语义等价已验证：两个变体的 `answer.json` **逐字段相同**（`distance_km = 3878.27`）。

| 数据 | O | R |
|---|---|---|
| 出厂 | 0.667 | **1.000** |
| 对抗 | **1.000** | 0.667 |

**未触发**：12 次运行 **0 次 KeyError**；每个 run 都由运行时探 schema 化解。
两处 0.667 的失败都是同一个**无关**的 agent 手滑：时间戳写成
`2024-02-09T20:06:31.660000Z`（`isoformat()` 保留微秒），而 task/verifier 要求整秒 `...31Z`。
两次失败分别落在不同变体、不同 skill 臂 → Fisher **p = 1.000**。

### 02 · grid-dispatch-operator —— **触发，但方向相反**

确定性机制（本地 LP 计算，0 次模型调用）：评分器口径最优 **200 $/h** vs 经济正确 **5,000 $/h**，**25× 差距 / +2400%**（容差 ±0.01%）。

| 数据 | O | R |
|---|---|---|
| base | 0.667 | **1.000** |
| type1 | **1.000** | 0.333 |

**方向相反**：原版文档的 Type-1 声明是**惰性**的（type1 上 3/3 O 运行忽略 MODEL、上报 200、全过）；
**是我的"最小修复"促发了失败** —— 修复文本显式提到 MODEL 列，2/3 运行去解析它、算出正确成本 5000 → 被评分器判超下限。
`RepairedSkill__r3` 轨迹里明确写着 `model = int(cost_row[0])  # 1=piecewise, 2=polynomial`。
→ 教训 **P6**：评分器与实现共享同一误读时，让文档"更严谨"会降低测得成功率。

### 03 · pddl-tpp-planning —— **未触发**

机械证明（纯 Python，无容器）：`task01.txt` → 文本（正常）；`task01.plan` / `task01` → **二进制 pickle，文本被销毁**。

| 数据 | O | R |
|---|---|---|
| `.txt` | **1.000** | 0.667 |
| `.plan` | 0.667 | **1.000** |

**未触发**：轨迹里 `pickle` / `.pkl` **出现 0 次**；verifier 从未报解码错误
（若计划文件是 pickle，文本模式 `open()` 必然抛 `UnicodeDecodeError`）。
实际失败是"计划内容不合法"与"输出文件没写全"。**agent 自己写保存代码，不执行 `.skill` 文件。**
→ 教训 **P7**：机制落在实现文件里 = 永不执行。

### 04 · energy-unit-commitment —— **触发且确定致败** ⭐

`SKILL.md` 同一段代码里，`alloc` 的函数体从不读 `lb/ub/integer`，而调用点写着 `lb=0, ub=1, integer=True`。

| cell | reward | 产出 report | commitment 越界值 |
|---|---|---|---|
| O r1 | 0.0 | ✓ | 0 |
| **O r2** | **0.0** | **✓** | **36** |
| O r3 | 0.0 | ✗ | — |
| R r1 / r2 / r3 | 0.0 / 0.0 / 0.0 | ✓ / ✗ / ✓ | 0 / — / 0 |

- **6/6 运行照抄了文档里的 `alloc`**（`uses_alloc = 3/3 + 3/3`）。
- 越界值：`123_STEAM_3` hour41=**3.0**、hour44=**4.0**；`121_NUCLEAR_1` hour17=**2.0**；共 36 个。
- verifier：`AssertionError: 123_STEAM_3 commitment contains values other than 0/1`。
- 修复臂 2 份 report **0 个越界值**，其中 2/3 运行照抄了修好的 helper。

**O → R：非二值 report 1/2 → 0/2。** 这是**唯一**「影响确定 + repair 规避」的案例。
**边界**：每臂仅 2 份 report；两臂 reward 都是 0.0（任务在成功率地板上），结论限定在校验层。
→ 这是 **P7** 的正向验证：触发点落在**文档里可复制的代码块**时，agent 一定会执行到它。

### 05 · multilingual-video-dubbing —— **仅机制证明**

`SKILL.md` 的 "Peak normalization" 注释说"用探测到的峰值归一化"，命令却写死 `volume=0.5`（恒定 **−6.02 dB**）。

| 源 LUFS | 施加 volume=0.5 后 | 合规（−24.5 ~ −21.5）？ |
|---|---|---|
| −14.0 | −20.02 | ✗ |
| −18.0 | −24.02 | ✓ |
| −23.0 | −29.02 | ✗ |
| −29.0 | −35.02 | ✗ |
| −35.0 | −41.02 | ✗ |

任务要求 #1 就是 ITU-R BS.1770-4，verifier 断言 `-24.5 <= measured_lufs <= -21.5`。
**只在源恰好 ≈ −17 LUFS 时才合规**，而源是 TTS 输出，不受控。
实验未跑（镜像含 CPU 版 Torch + pyopenjtalk 编译，成本高）。

### 06 · sales-pivot-analysis —— **reward 差异存在，但归因失败**

| 条件 | scores | 均值 |
|---|---|---|
| O | 0.0 / 1.0 / 0.0 | **0.333** |
| R | 1.0 / 1.0 / 1.0 | **1.000** |

看似 +0.667 的大成功，但：

1. **6/6 运行从未用过 `pivotFields[1]`**（O r2 用的是自己算的 `RowColField(x=2/6/7)`）。
2. O 的两次失败是 `IndexError: _pivots[0]` —— **agent 根本没建任何透视表对象**；
   第三次还是 `Missing POPULATION_2023` / `Invalid quarter values: {'Unknown'}`。
3. 真实自变量是**文档可执行性**：修复臂示例更完整，3/3 都真的调用了 pivot API；原臂 2/3 完全没调用。

→ 教训 **P8**：修复 diff 混入"让示例更能跑"的改动时，你测的是文档质量，不是目标不一致性。

### 07 · lab-unit-harmonization —— **触发，但效果被淹没**

出厂数据本身已含 **423 个 1–5% 近边界值**，无需数据扰动。

| cell | reward | 区间外总数 | **1–5%** | >5% | 写了钳制代码 |
|---|---|---|---|---|---|
| O r1 | 0.542 | 14239 | 169 | 14070 | ✗ |
| O r2 | 0.958 | 2788 | **0** | 2788 | ✗ |
| O r3 | 0.312 | 21049 | 424 | 20625 | ✗ |
| R r1 | 0.333 | 18663 | 396 | 18267 | **✓** |
| R r2 | 0.458 | 13405 | 39 | 13366 | **✓** |
| R r3 | 0.604 | 9245 | 39 | 9206 | **✓** |

| 条件 | 平均 reward | 中位 1–5% 残留 | 写了钳制代码 |
|---|---|---|---|
| O | 0.604 | **169** | **0/3** |
| R | 0.465 | **39** | **3/3** |

**机制确实触发**（0/3 → 3/3，残留 169 → 39），但 reward **反向且 p = 1.000** ——
主导失败是每次 **1–2 万个值根本没做单位换算**，钳制只影响几百个，量级差两个数量级。
→ 教训 **P9**：**触发**与**可测量**必须分开报。

### 08 · adaptive-cruise-control —— **机制证明完成，实验被叫停**

`SKILL.md` 的可复制 `compute()` 无条件积分，而紧随其后的 "Anti-Windup" 一节列了三种方案却一个都没实现。
任务本身**逼出饱和**（0→27 m/s 在 |a|≤3.0 下必须满加速约 9 秒）。

本地确定性仿真（复刻 verifier 的三个阈值：rise<10s、`max(ego_speed)<31.5`、`|30−mean(25–30s)|<0.5`）：

| 增益 (kp,ki,kd) | 无抗饱和 | 有抗饱和 |
|---|---|---|
| (2.0, 0.1, 0.5) | 超调 **22.7%** / SS 2.98 → FAIL | 0.2% / 0.03 → **PASS** |
| (1.0, 0.05, 0.2) | **22.1%** / 3.02 → FAIL | 0.6% / 0.09 → **PASS** |
| (4.0, 0.3, 1.0) | **32.6%** / 2.65 → FAIL | 0.2% / 0.27 → **PASS** |
| (0.5, 0.02, 0.1) | **17.1%** / 3.08 → FAIL | 0.6% / 0.13 → **PASS** |

**四种增益下结论完全一致**，不依赖调参 → 这是目前机制最稳的一个。
实验在 3 个 OriginalSkill cell 跑到中途被叫停（status `agent_running`，无分数），**无 O/R 对比数据**。

---

## 三、汇总读出的三件事

### 1. reward 层面的 O/R 差异**全部不可归因**

七个实验的 delta：

| # | O → R | 问题 |
|---|---|---|
| 01 | 0.667→1.000 / 1.000→0.667 | 无关的时间戳格式手滑，p=1.000 |
| 02 | 0.667→1.000 / 1.000→**0.333** | 修复**制造**失败（P6） |
| 03 | 1.000→0.667 / 0.667→1.000 | 未触发，纯噪声 |
| 04 | 0.000→0.000 | 任务在 reward 地板，只有校验层信号 |
| 06 | 0.333→**1.000** | 混杂：真实自变量是文档可执行性（P8） |
| 07 | 0.604→0.465 | 被主导失败模式淹没，p=1.000（P9） |
| 08 | — | 被叫停 |

**没有任何一个 delta 可以归因于被修复的不一致性。** 这本身就是最重要的结论：
n=3 的 reward 对比在这个 benchmark 上被无关噪声、混杂变量和量级淹没三重问题支配。

### 2. 可靠的证据只在**产出物层**

| 案例 | 产出物级证据 | 强度 |
|---|---|---|
| 04 | commitment = 3.0/4.0，verifier 点名 `123_STEAM_3` | **最强**（确定致败）|
| 07 | 钳制代码 0/3→3/3；近边界残留 169→39 | 强（行为改变确定）|
| 02 | 上报成本 3/3=200 vs 2/3≠200 | 强（机制确定）|
| 01 / 03 | 0 次 KeyError / 0 次 pickle | 强（**证伪**）|
| 06 | 6/6 未用 `pivotFields[1]`，2/3 未建 pivot | 强（**归因失败**）|

### 3. 触发位置决定一切（P7）

| 机制藏在 | 触发率 | 案例 |
|---|---|---|
| `.skill` / `scripts/` 实现文件 | **0/1** | 03（agent 自己写保存代码）|
| 文档示例与数据 schema 冲突 | **0/1** | 01（运行时探 schema 即化解）|
| 文档示例的硬编码索引 | 0/1（且混杂） | 06 |
| **文档里可复制的代码块 / 命令** | **3/3** | **04、07、08（机制）** |
| 参考文档与**评分器**共享同一误读 | 触发但反向 | 02 |

---

## 四、原始证据索引

| # | 实验目录 | 判定脚本 | 报告 |
|---|---|---|---|
| 01 | `experiments/earthquake-adv-20260924/` | `analysis_tools/eq_adv_analyze.py` | `adversarial/01-field-name-shadowing/` |
| 02 | `experiments/grid-type1-adv-20260924/` | `analysis_tools/grid_type1_analyze.py` | `adversarial/02-silent-format-misread/` |
| 03 | `experiments/pddl-planpath-adv-20260924/` | `analysis_tools/pddl_planpath_analyze.py` | `adversarial/03-undeclared-side-effect/` |
| 04 | `experiments/uc-alloc-adv-20260924/` | `analysis_tools/uc_alloc_analyze.py` | `adversarial/04-copied-helper-semantics/` |
| 05 | （未跑） | `adversarial/05-.../builder/prove_fixed_gain.py` | `adversarial/05-fixed-gain-vs-normalization/` |
| 06 | `experiments/pivot-fieldindex-adv-20260924/` | `analysis_tools/pivot_fieldindex_analyze.py` | `adversarial/06-field-index-confounded/` |
| 07 | `experiments/labclamp-adv-20260924/` | `analysis_tools/lab_clamp_analyze.py` | `adversarial/07-clamp-swamped/` |
| 08 | `experiments/acc-windup-adv-20260924/`（3 个未完成 cell） | `analysis_tools/acc_windup_analyze.py` | `adversarial/08-pid-windup/` |

构造原则 P1–P9 见 `adversarial/README.md`；
「哪些不一致性产生了确定影响且 repair 规避了它」见 `adversarial/SUMMARY-actual-impact-and-repair.md`。
