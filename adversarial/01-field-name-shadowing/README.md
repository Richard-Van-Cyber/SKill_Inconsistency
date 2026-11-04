# 01 · 字段名遮蔽（field-name shadowing）

**目标不一致性**：`earthquake-plate-calculation` 的技能文档 `geospatial-analysis/SKILL.md`
同时对同一件事给出三套互斥写法，且没有说明哪套属于哪个文件：

| 文档中的写法 | 出厂数据 `PB2002_plates.json` | 对抗数据 |
|---|---|---|
| `gdf_plates["Name"] == "Pacific"`（Finding Points Within a Polygon 一节） | ✗ KeyError（该文件没有 `Name`） | ✓ 命中 |
| `gdf_plates["PlateName"] == "Pacific"`（Filtering by Attributes 一节） | ✓ 命中 | ✗ KeyError |
| `gdf_plates["Code"] == "PA"`（Common Workflow Pattern 一节） | ✓ 命中 | ✓ 命中 |

而 `PB2002_boundaries.json` 恰好**有** `Name` 列 —— 两个文件列名不同构，文档把它们混着用。

## 对抗数据怎么造

**语义等价扰动**：只把 `PB2002_plates.json` 每个 feature 的 `PlateName` 键改名为 `Name`。
几何、数值、`Code` 全部不动。

**语义保持性已实测**：用 schema-robust 的 oracle（把选板条件改成 `Code == "PA"`）
在两个数据变体上跑，输出 `answer.json` **逐字段完全一致**
（`distance_km = 3878.27`，与 verifier 硬编码的 ground truth 相同）。因此 verifier 无需改动。

## 最小修复

只动 3 行 + 加 1 条说明，全部改成用 **两个 schema 都存在** 的 `Code`：

```diff
- target_poly = gdf_plates[gdf_plates["Name"] == "Pacific"].geometry.unary_union
+ target_poly = gdf_plates[gdf_plates["Code"] == "PA"].geometry.unary_union
- pacific_plate = gdf_plates[gdf_plates["PlateName"] == "Pacific"]
+ pacific_plate = gdf_plates[gdf_plates["Code"] == "PA"]
- geometry = [Point(eq["longitude"], eq["latitude"]) for eq in earthquakes_data]
+ geometry = [Point(pt["coordinates"][0], pt["coordinates"][1]) for pt in earthquakes_data]
+ > **Column note.** PB2002_plates.json 用 Code；PB2002_boundaries.json 用 Name；两者不共享名称列。
```

## 配对实验结果（各 3 trial，60 req / 1M tok / 32K out）

| 数据变体 | OriginalSkill | RepairedSkill |
|---|---|---|
| 出厂（plates 用 `PlateName`） | 0.667（10 calls / 289k tok） | **1.000**（6 calls / 160k tok） |
| 对抗（plates 用 `Name`） | **1.000**（7 calls / 193k tok） | 0.667（6 calls / 165k tok） |

2×2 看起来像漂亮的交互效应，但**逐条核对后判定为噪声**：

1. **12 次运行里 0 次 KeyError。** 对抗数据从未把不一致性逼出来。
2. 两次失败（shipped+Orig r3、adv+Rep r3）的 pytest 输出都是
   `test_time_correct: '2024-02-09T20:06:31.660000Z' != '2024-02-09T20:06:31Z'`
   —— **ISO 8601 毫秒格式问题**，与选板字段名无关；另有一次附带 `test_distance_within_tolerance` 未过。
3. 效率差异（Original 10 calls vs Repaired 6 calls）在两个数据变体上方向一致，
   更像是「修复后的文档更明确」带来的普遍收益，而不是被触发的不一致性造成的。

## 结论：这条构造**失败**了，失败原因就是构造原则

agent 在写脚本前会 `ls` / `Read` / `print(keys())` 把数据 schema 看一遍。
**一个 `print(df.columns)` 就能发现的文档错误，不构成有效触发器。**
`Name` / `PlateName` / `Code` 三者在运行时都唾手可得，所以文档写错哪个都无所谓。

保留此目录作为**反例**：它证明了「字段名遮蔽」这一构造模式在本 benchmark 上无效。

## 补充：RepairedSkill 那一次失败到底是什么原因

2×2 里 `adv + RepairedSkill = 0.667` 看起来像"修复在对抗数据上失效"，
**但那一次失败与修复、与选板字段名都没有关系。**

把 12 次运行产出的 `answer.json` 逐个打开对比：

| 运行 | score | 写入的 time | 正确？ |
|---|---|---|---|
| adv · Original r1/r2/r3 | 1.0 | `2024-02-09T20:06:31Z` | ✓ |
| adv · Repaired r1/r2 | 1.0 | `2024-02-09T20:06:31Z` | ✓ |
| **adv · Repaired r3** | **0.0** | **`2024-02-09T20:06:31.660000Z`** | ✗ |
| shipped · Original r1/r2 | 1.0 | `2024-02-09T20:06:31Z` | ✓ |
| **shipped · Original r3** | **0.0** | **`2024-02-09T20:06:31.660000Z`** | ✗ |
| shipped · Repaired r1/r2/r3 | 1.0 | `2024-02-09T20:06:31Z` | ✓ |

**12 次运行全部找对了地震、算对了距离**（`distance_km = 3878.27`），
唯一的差别是时间戳字符串。两次失败写的是**完全相同的错串**，
而且分别落在**不同的数据变体、不同的 skill 臂**上 —— 这是随机手滑的特征，不是处理效应。

### 机制

```python
# 原始数据
props["time"] = 1707509191660          # 毫秒
1707509191660 / 1000 = 1707509191.66   # 秒，带小数
```

- **失败的两次**用 `datetime.utcfromtimestamp(ts).isoformat() + 'Z'`
  → 保留微秒 → `2024-02-09T20:06:31.660000Z`
- **通过的那次**用 `dt.strftime('%Y-%m-%dT%H:%M:%SZ')`
  → 截断到秒 → `2024-02-09T20:06:31Z`

而 task.md 明确要求 `YYYY-MM-DDTHH:MM:SSZ`（无小数部分），
verifier 又是 `assertEqual` 精确比对 —— 所以是**任务侧的格式陷阱**，
与 `geospatial-analysis`（一个纯几何/投影的技能，完全不涉及时间）毫无关系。

### 统计

| 对比 | Fisher 精确检验 |
|---|---|
| adv：Original 0/3 失败 vs Repaired 1/3 失败 | p = 1.000 |
| shipped：Original 1/3 vs Repaired 0/3 | p = 1.000 |
| Repaired：shipped 0/3 vs adv 1/3 | p = 1.000 |
| 合并：Original 1/6 vs Repaired 1/6 | p = 1.000 |

与这个无关故障的基线发生率（**2/12 = 16.7%**）完全一致。
**n=3 时，reward 层面的差异被这类无关陷阱完全淹没** ——
这正是本系列坚持做**产出物级分类**而不是只看 reward 的原因。

## 文件

| 文件 | 内容 |
|---|---|
| `data/PB2002_plates.adv.json` | 对抗数据（`PlateName` → `Name`） |
| `repair/SKILL.original.md` | 原技能文档 |
| `repair/SKILL.repaired.md` | 最小修复后的技能文档 |
| `evidence/eq_adv_analyze.py` | 轨迹分析脚本（统计 idiom 使用与 KeyError） |
| `evidence/analysis.json` | 12 个 cell 的逐条指标 |
