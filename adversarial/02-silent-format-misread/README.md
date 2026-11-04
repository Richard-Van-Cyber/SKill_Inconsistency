# 02 · 静默格式误读（silent format misread）—— **构造成功**

**目标不一致性**：`grid-dispatch-operator` 的 `economic-dispatch/references/cost-functions.md`
把 MATPOWER **Type 1 分段线性成本**列为受支持格式并给出示例；
而技能的 `SKILL.md` 目标函数**只按 NCOST 分支**，从不读 `gencost[i, 0]`（MODEL 列）。

**关键发现**：任务 verifier 的 `optimal_cost` fixture 犯**同一个错** ——
`c2, c1, c0 = gencost[i,4], gencost[i,5], gencost[i,6]`。
即**技能与评分器以同样错误的方式读数据**。这决定了本案例的因果方向与直觉相反。

---

## 一、为什么这个构造满足三个必要条件

| 条件 | 本案例 |
|---|---|
| **C1 数据依赖** | 只有数据里出现 MODEL=1 行才走错分支。出厂 510 台机组全是 MODEL=2 → bug 休眠 |
| **C2 静默** | 走错分支**不报错**：断点被当成 c2/c1/c0，算出一个貌似合理的成本与调度 |
| **C3 不可探知** | 正确语义只能来自 MATPOWER 规范；**输入里看不出来**，评分标准里也看不出来（评分器自己也错了） |

对比 01 号（字段名遮蔽）：那个一眼 `print(df.columns)` 就能识破，所以失败。
**C2 + C3 是有效触发的分水岭。**

---

## 二、对抗数据怎么造（语义等价，已机器验证）

因为原任务 2869 节点、成功率在地板上、reward 层面观察不到，我**把实例缩小到可解规模**，
保持 MATPOWER schema 完全一致：

- 3 母线 / 3 机组 / 3 线路，负荷 250 MW，备用需求 120 MW
- `gencost` 统一补齐到 **10 列**（Type-1 需要 `4 + 2*ncost` 列；真实 MATPOWER 矩阵本来就是矩形）

**两种读法的差距（用 verifier 的精确模型 + 线性规划算出，见 `builder/solve_small.py`）**：

| | base（全 MODEL=2） | type1（G2/G3 重编码为共线 Type-1） |
|---|---|---|
| 评分器口径最优（忽略 MODEL） | 5,000.00 $/h | **200.00 $/h** |
| 经济上正确的最优（按断点解读） | — | **5,000.00 $/h** |
| 差距 | — | **+2400%**（容差 ±0.01%） |
| 比值 | — | **25×** |

**共线编码**：G2 的 `c1=35` 写成断点 (0,0)/(100,3500)/(200,7000)，G3 同理。
三个点在同一条直线上 → **真实成本函数完全不变**，base 与 type1 的真实最优解**逐字段相同**
（dispatch [250,0,0]，reserve [50,50,50]，成本 5000）。所以 verifier 的 ground truth 不需要改，
失败可以无歧义归因。

**评分器的误读**：读 `gencost[i,4:7]` = `(0, 0, 100)` → 认为 G2/G3 是**固定成本 100 的免费电源** →
把负荷全推给它们，算出 200 $/h。

---

## 三、最小修复，以及它**反向生效**了

我按 P4「基准 = 任务 + verifier」写了一版最小修复：把 Type-1 那一节替换成
「不支持 Type-1；请把每台机组表达为 MODEL=2」。

**结果它在 type1 上把成功率从 1.000 拉到 0.333。**

因为 agent 把「express every generator as MODEL=2」理解成**指令**，
于是真的去**转换数据**、把 MODEL=1 行还原成线性多项式，算出**正确**的 5000 —— 评分器判它失败。

---

## 四、配对实验结果（各 3 trial，60 req / 1M tok / 32K out）

| 数据变体 | OriginalSkill | RepairedSkill |
|---|---|---|
| base | 0.667 | **1.000** |
| type1 | **1.000** | **0.333** |

**逐条产出物分类（这是真正的证据，与 reward 噪声无关）**：

| 数据变体 | 条件 | 上报成本 | 判读 |
|---|---|---|---|
| type1 | OriginalSkill ×3 | **200 / 200 / 200** | 全部**忽略 MODEL**，与评分器一致 → 全过 |
| type1 | RepairedSkill | 200 / **2200** / **5000** | 2/3 真的去解析 MODEL → 算出正确成本 → 失败 |
| base | OriginalSkill | 11000 / 5000 / 5000 | r1 是 agent 自身错误（调度 [0,100,150]）|
| base | RepairedSkill ×3 | 5000 / 5000 / 5000 | 全过 |

### 轨迹里的机制（`RepairedSkill__r3`）

```python
model = int(cost_row[0])  # 1=piecewise, 2=polynomial
"""Parse MATPOWER cost function format (piecewise linear)."""
```

agent **确实实现了分段线性解析**，上报 5000 → 评分器期望 200 → `gap=+2400%` → 失败。

### 因果方向与直觉相反

- **原始文档的那条不一致性本身是惰性的**：3/3 的 OriginalSkill 运行压根没去用
  `cost-functions.md` 的 Type-1 段，直接照抄 `gencost[:,4:7]` → 与评分器一致 → 全过。
- **是我的「修复」把冲突激活了**：修复文本显式提到 MODEL 列，反而促使 agent 去解析它。

**修正后的结论**：在本案例里，让技能文档**更精确**会**降低**测得成功率，
因为评分器与实现共享同一个误读。此时唯一能通过的最小修复不是「让文档更严谨」，
而是**显式告诉 agent 盲读 `gencost[:,4:7]`、不要检查 MODEL** ——
即彻底对齐到评分器语义（哪怕它在 MATPOWER 语义上是错的）。

> 统计上要谨慎：n=3，reward 层面 gap 的 Fisher 精确检验 p≈0.2，**不显著**。
> 但产出物层面的分类（3/3 上报 200 vs 2/3 上报 ≠200）是无歧义的机制证据。

---

## 五、文件

| 文件 | 内容 |
|---|---|
| `data/network_small.json` | base 数据（全 MODEL=2） |
| `data/network_small_type1.json` | 对抗数据（G2/G3 共线 Type-1 重编码） |
| `builder/build_small.py` | 构造脚本（含共线编码） |
| `builder/solve_small.py` | 用 verifier 的精确模型算出两种口径的最优解与差距（**决定性证据，0 模型调用**） |
| `repair/cost-functions.original.md` | 原参考文档（声明支持 Type-1） |
| `repair/cost-functions.repaired.md` | 我的最小修复（**已证明反向生效**） |
| `evidence/analysis.json` | 12 个 cell 的上报成本、调度与判读 |
| `evidence/grid_type1_analyze.py` | 分析脚本 |
