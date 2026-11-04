# 对抗性任务构造：原则、已构造案例与触发结果

本目录保存**构造成功的对抗任务数据**、**构造原则**，以及**构造失败的案例**（同样是证据）。

配套报告：
- `adversarial-trigger-round1.md` —— 目标筛查、机械一致性探针方法、finding 三分类
- `adversarial-trigger-pilot-mario.md` —— mario 试点（5 条 finding，0 条可触发）
- `skill_inconsistency_impact_top30.md` / `skill_trace_causal_audit.md` —— 87 任务的影响排序与轨迹因果判决

---

## 一、判定「有没有触发」的方法：两层证据，先廉价后昂贵

### 第 1 层 · 机械一致性探针（0 次模型调用）

每条 finding 的触发条件几乎都能在真实任务镜像里用一条确定性命令证伪：

```bash
ssh user@10.0.0.64 \
  'docker run --rm -v /tmp/adv_probe:/w <image> bash /w/<probe>.sh'
```

检查项：环境版本与二进制（ffmpeg / ImageMagick / 已装包）、文档给出的命令能否执行、
脚本在给定数据上的行为。**先用这层筛掉「条件不成立」的 finding，再谈 agent 实验。**

### 第 2 层 · 配对 agent 实验

```
{出厂数据, 对抗数据} × {original skill, 最小修复 skill} × 3 trial
```

判定触发不能只看 reward。必须同时满足：

| 证据 | 判据 |
|---|---|
| **E1 运行时错误** | 轨迹里出现指向该 finding 的异常（KeyError / ImportError / TimeoutError） |
| **E2 语义偏离** | 产出物在**被影响的那一项**上错了（不是别的项） |
| **E3 修复可逆** | 只改文档/一行代码后，同一对抗数据下该错误消失 |

**只满足 reward 差异不算触发。** 第 01 号案例就是反例：2×2 的 reward 有差异，
但逐条核对 pytest 输出后，两次失败都是 `test_time_correct`（ISO 毫秒格式），与目标 finding 无关。

---

## 二、构造原则

### P1 · 语义等价扰动（semantics-preserving perturbation）

只改**表示**，不改**答案**。数据扰动后必须用 schema-robust 的 oracle 在两个变体上各跑一遍，
断言输出逐字段一致。这样 verifier 的 ground truth 无需改动，失败可**无歧义**归因。

> 01 号案例执行到了这一步：两个变体的 `answer.json` 完全相同（`distance_km = 3878.27`）。

### P2 · 触发条件必须是**数据**决定的，不是**环境**或**agent 行为**决定的

87 个任务的 finding 可分三类，只有 C 类适合「对抗性任务数据」这条路线：

| 类别 | 触发由什么决定 | 数据扰动能否逼出 | 例 |
|---|---|---|---|
| **A 条件式环境假设** | 环境版本 / 已装包 / 二进制 | ✗ 要改**镜像** | mario F-001 `convert` vs IM7；F-003 `-vsync` vs ffmpeg 7 |
| **B agent 行为依赖** | agent 是否照抄文档的调用约定 | ✗ 与数据无关 | dialogue-parser F-003（`Node` 参数顺序）；crystallographic F-001 |
| **C 数据格式依赖** | 输入数据用哪种格式/取值 | ✓ **可以** | grid-dispatch F-002（MATPOWER Type-1 gencost） |

### P3 ·（最重要，从失败中学到的）**正确行为不能在运行时被廉价发现**

> 一个 `print(df.columns)` 就能发现的文档错误，不构成有效触发器。

01 号案例正是死在这一条：agent 在写脚本前会 `ls` / `Read` / 打印 schema，
`Name` / `PlateName` / `Code` 三者都唾手可得，所以文档写错哪个都无所谓 ——
**12 次运行 0 次 KeyError**。

因此有效的 C 类构造必须满足**三个子条件同时成立**：

| 子条件 | 含义 | 反例 |
|---|---|---|
| **C1 数据依赖** | 只有特定格式/取值的输入才走错分支 | — |
| **C2 静默** | 走错分支**不报错**，产出看起来合理的数字 | 字段名遮蔽（会 KeyError，可被发现） |
| **C3 不可探知** | 正确语义**不能**通过检查输入发现，只能来自领域知识或评分标准 | 任何 schema 可见的差异 |

### P4 · 最小修复 + 基准统一

修复只改不一致性本身，基准是**任务 + verifier**（不是「让 skill 更强」）。
如果 verifier 与 skill 犯同一个错（grid 的 Type-1 就是这种情况：两边都忽略 `MODEL` 列），
那么「正确实现参考文档」的 agent 反而会被判失败 —— 此时唯一能通过的最小修复是
**把文档的过度承诺删掉/对齐到评分器的语义**，而不是把实现改对。
这个方向必须在报告里写明，否则修复会被误判成「改坏了」。

### P5 · 保存可复现的三件套

每个对抗任务必须落盘：**(a) 对抗数据本身**、**(b) 最小修复后的 skill**、
**(c) 原始轨迹 + 判定脚本**。缺任何一件，结论都无法复核。

---

## 三、已构造案例与触发结果

| # | 任务 | 构造模式 | 数据扰动 | 触发结果 | 目录 |
|---|---|---|---|---|---|
| 01 | `earthquake-plate-calculation` | 字段名遮蔽（三套互斥列名） | `PB2002_plates.json` 的 `PlateName` → `Name` | **✗ 未触发**（12 run / 0 KeyError） | `01-field-name-shadowing/` |
| 02 | `grid-dispatch-operator` | **静默格式误读**（MATPOWER Type-1 gencost 被技能与评分器同时误读） | 缩小实例 + 把纯线性成本**共线重编码**为 Type-1 行 | **✓ 触发**（type1 上 3/3 上报 200 vs 2/3 上报 2200/5000；reward 1.000 → 0.333） | `02-silent-format-misread/` |
| 03 | `pddl-tpp-planning` | **未声明的副作用**（`save_plan` 用 `path.replace('.txt','.pkl')` 覆盖自身） | `plan_output` 的扩展名 `.txt` → `.plan` | **✗ 未触发**（verifier 无解码错误；轨迹里 `pickle` 出现 0 次） | `03-undeclared-side-effect/` |
| 04 | `mario-coin-counting` | 环境条件式（`convert`/ffmpeg7/缺 cv2） | 无需扰动，改环境才行 | **✗ 未触发**（5 条 finding 条件全为假；skill 在出厂数据上 8/8 正确） | 见 `adversarial-trigger-pilot-mario.md` |
| 04 | `energy-unit-commitment` | **被照抄的辅助函数语义**（`alloc` 丢弃 `lb/ub/integer`） | 处理是技能文档，非数据 | **✓ 触发**：6/6 运行照抄了 `alloc`；1/2 原版 report 出现 commitment = 2.0/3.0/4.0（36 个）→ verifier `contains values other than 0/1` 失败；修复臂 0/2 | `04-copied-helper-semantics/` |
| 05 | `multilingual-video-dubbing` | **固定增益冒充归一化**（`volume=0.5` = 恒定 −6 dB） | 源电平恰好 −17 LUFS 才合规 | **机制证明完成**（实验未跑，镜像构建成本高） | `05-fixed-gain-vs-normalization/` |
| 06 | `sales-pivot-analysis` | 同一索引 1 被标为 ProductName / Quarter | 处理是技能文档 | **✗ 归因失败（混杂）**：reward 0.333 → 1.000，但 6/6 运行都没用过 `pivotFields[1]`；真正的自变量是文档可执行性 | `06-field-index-confounded/` |
| 07 | `lab-unit-harmonization` | 正文承诺 5% 钳制 / 代码块写死 NO CLAMPING | 无需扰动（出厂数据已有 423 个 1-5% 近边界值） | **✓ 触发但不可测量**：钳制代码 0/3 → 3/3、近边界残留中位 169 → 39；reward 反被 >5% 主导失败淹没（p=1.000） | `07-clamp-swamped/` |

**01 号失败原因**：违反 P3。字段名在运行时可见，agent 一定会先探 schema 再写代码。

### P7 ·（根因）agent 把 skill 当**文档**读，不当**代码**执行

四个构造的一致结论：agent 读 `SKILL.md` 了解流程，然后**自己写脚本实现该流程**。

| 机制藏在哪里 | 会不会被触发 |
|---|---|
| `.skill` / `scripts/` 等**实现文件**里的 bug | ✗ 永不执行（03 号：`pickle` 在轨迹里 0 次） |
| **文档与数据 schema 不一致** | ✗ 运行时探查即化解（01 号：0 次 KeyError） |
| **文档主动改变 agent 的实现选择** | ✓ 会生效（02 号：修复文本促使 agent 解析 MODEL） |
| **文档里 agent 会照抄的代码块** | ✓✓ 先验最高（04 号：照抄 `alloc` → commitment 取到 2.5/6.0） |

**构造策略**：扰动必须落在 **agent 会照抄的那份文本**（`SKILL.md` 的流程、公式、参数、默认值），
而不是它不会执行的脚本实现里。这条把 87 个任务的 finding 又筛掉一大半：
凡是证据指向 `.py` / `.skill` / `.mjs` 等实现文件的，先验概率都很低。

### P9 · **触发**与**可测量**是两件独立的事，必须分开报

07 号同时给出了两个相反方向的判决：

| 判定 | 证据 | 结果 |
|---|---|---|
| 是否触发 | 修复臂 3/3 写了钳制代码（原臂 0/3）；近边界残留中位 169 → 39 | **✓ 是** |
| 效果多大 | reward 0.604 → 0.465，p=1.000；而每只有几百个近边界值，却有 1-2 万个值根本没做单位换算 | **✗ 被淹没** |

**规则**：先判触发（agent 行为是否真的变了），再判效果（该行为在任务误差预算里占多大份额）。
影响量级远小于任务主导失败模式的 finding，即使机制完美触发，也不能写进 effectiveness 结论。

### P8 · 修复必须是**单变量**的，否则你测的是文档质量

06 号实测到的坑：我把二维透视表示例从"硬编码索引"改成"按名字查索引"时，
顺带让示例**更完整、更可运行**（补全了 axisRow/axisCol/dataField 与 rowFields/colFields/dataFields 的整条链路）。
结果修复臂 3/3 都真的调用了 pivot API，原臂有 2/3 根本没调用 ——
reward 差异 +0.667 看似很大，但自变量是**可执行性**而不是目标不一致性。

**规则**：修复 diff 只准包含目标不一致性本身。若为了让示例能跑而补了别的东西，
必须再加一个"只改那一行"的第三臂，否则不能归因。

### P6 · 当评分器与实现共享同一个误读时，「让文档更严谨」会**反向生效**

02 号案例实测到的反直觉结果：我把参考文档里的 Type-1 声明改成
「不支持 Type-1，请把每台机组表达为 MODEL=2」之后，agent 把这句话当成**指令**，
真的去转换数据、算出**经济上正确**的成本 —— 而评分器仍在误读，于是判它失败。
**成功率从 1.000 掉到 0.333。**

因此在「基准 = 任务 + verifier」的前提下判断最小修复时，必须先问一句：
**评分器自己是对的吗？** 若评分器与实现犯同一个错，唯一能通过的最小修复是
**让文档彻底对齐评分器语义**（本例：明确要求盲读 `gencost[:,4:7]`、不要检查 MODEL），
而不是「把文档写得更符合规范」—— 后者会让 agent 做出正确但被判错的行为。

**由此修正出的、值得继续尝试的构造模式**（满足 C1+C2+C3）：

| 模式 | 为什么满足 C2/C3 | 87 任务中的落点 |
|---|---|---|
| **静默的语义/单位重编码** ✅ 已在 02 号验证 | 输入格式合法、无报错，但错误分支产出貌似合理的数值；正确语义来自评分标准而非输入 | `grid-dispatch-operator` F-002（见 `02-silent-format-misread/`）：**25× 差距**，+2400% 超出 ±0.01% 容差 |
| **默认值/阈值分歧** | 文档写 600、实现是 120，只有跑起来超时才暴露 | `latex-formula-extraction` F-001：轨迹里已实测到 `timed out after 120s` ×4 与 `timed out after 600s` ×2 |
| **未声明的输入约束** | 数据合法但落在文档未声明的边界外，静默产生 NaN/丢行 | `lab-unit-harmonization`（注：task.md 明说 `,` 是小数点，塞千位分隔符会与任务说明冲突，需先论证合法性） |

---

## 四、复现方式

```bash
# 01 号案例的配对实验（服务器已有镜像）
ssh user@10.0.0.64
cd /home/user/project/experiments/earthquake-adv-20260924
/home/user/project/.venv-benchflow/bin/python runner-source/adv_run.py --workers 3
# 结果落在 runs/<task>__<condition>__r<n>/，判定用 evidence/eq_adv_analyze.py
```

> 跑非原生 10 任务时需要两处 runner 扩展（已完成，均在 `runner-source/`）：
> `rq3_support.archive_artifacts` 的 `roots` 表、`verifier_dependencies.TASKS` + `EXTRA_DEPS`
> （新任务的 verifier 从 github 拉 uv，沙箱访问不到，必须由 runner 注入）。
