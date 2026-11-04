# 04 · 被照抄的辅助函数语义（copied-helper semantics）—— **构造成功、已触发**

**目标不一致性**：`energy-unit-commitment` 的 `milp-solver-workflow/SKILL.md`
在同一段代码里同时给出：

```python
def alloc(name, shape, lb=0.0, ub=float("inf"), integer=False):
    global n
    size = int(np.prod(shape))
    idx = np.arange(n, n + size).reshape(shape)
    offset[name] = idx
    n += size
    return idx                       # ← 函数体从不读 lb / ub / integer

u = alloc("commitment", (G, T), lb=0, ub=1, integer=True)
start = alloc("startup",    (G, T), lb=0, ub=1, integer=True)
dispatch = alloc("dispatch",(G, T), lb=0)
```

调用点声明了「0/1 二值与整数性」，函数体**静默丢弃**。

## 为什么这个案例在 P7 下先验很高

这是目前唯一一个**不一致性完全落在 agent 会照抄的那段代码里**的案例：

| | 01 earthquake | 03 pddl | **04 本案例** |
|---|---|---|---|
| 证据位置 | `SKILL.md` 三个互斥示例 | `.skill` 实现文件 | **`SKILL.md` 里的可复制代码块** |
| agent 会不会执行到 | 不执行，自己写 | 不执行，自己写 | **照抄进自己的脚本** |

## 机械证明（0 次模型调用）

`builder/prove_alloc.py` **直接从真实 `SKILL.md` 里正则抽取 `alloc` 定义**
（不是手抄），再按文档的调用点建一个 2 机 3 时段的 UC 松弛模型：

| | 目标值 | commitment u | 二值？ |
|---|---|---|---|
| **照抄文档的 helper** | **2,200** | `[[2.5, 6.0, 2.5], [0, 0, 0]]` | ✗ **FAILS** |
| 补上 `lb/ub/integer` | **3,100** | `[[1, 1, 1], [0, 1, 0]]` | ✓ passes |

脚本还会自动回答「函数体里出现过 lb/ub/integer 吗」→ **False**。

**读数**：照抄 helper 时 commitment 取到 **2.5 和 6.0** —— 对 0/1 指示变量而言物理上不可能；
目标值也从 3100 掉到 2200（在无界、无整数性的空间里"更便宜"）。

而任务 verifier 明确检查（`verifier/test_outputs.py:177-178`）：

```python
assert np.all(np.abs(arr - rounded) <= TOL_BINARY), f"{label} must be binary within tolerance"
assert np.all((rounded == 0) | (rounded == 1)),    f"{label} contains values other than 0/1"
```

→ **必然失败**。

## 三个必要条件

| 条件 | 本案例 |
|---|---|
| **C1 数据依赖** | 只要 agent 用 `alloc` 建 `u` 就触发；若 LP 松弛恰好整数则侥幸通过 —— 依赖算例 |
| **C2 静默** | 求解器返回 `optimal`，无任何报错 |
| **C3 不可探知** | 函数签名写着 `ub=1, integer=True`，从调用点看不出被丢弃；必须读函数体才会发现 |

## 最小修复

让 helper 真正登记边界与整数性（`repair/alloc.repaired.py`），
或在文档里显式提示"`alloc` 只做索引，边界与整数性需另行登记"。
**注意 P4**：task + verifier 是基准，verifier 要求二值，所以两种修复方向一致，没有 02 号那种反向风险。

## 配对 agent 实验（各 3 trial，60 req / 1M tok / 32K out，同一份出厂数据）

处理是**技能文档**（不是数据）：`OriginalSkill` = 原 `alloc`；`RepairedSkill` = 让 `alloc` 真正登记边界与整数性。

| cell | score | 产出 report | 越界 commitment | 目标值 |
|---|---|---|---|---|
| OriginalSkill r1 | 0.0 | ✓ | 0 | 1,225,905 |
| **OriginalSkill r2** | **0.0** | **✓** | **36** | **776,342** |
| OriginalSkill r3 | 0.0 | ✗ | — | — |
| RepairedSkill r1 | 0.0 | ✓ | 0 | 5,596,856 |
| RepairedSkill r2 | 0.0 | ✗ | — | — |
| RepairedSkill r3 | 0.0 | ✓ | 0 | 1,212,501 |

| 条件 | 产出 report | 其中 **非二值** | 照抄了 `alloc` |
|---|---|---|---|
| OriginalSkill | 2/3 | **1/2** | 3/3 |
| RepairedSkill | 2/3 | **0/2** | 3/3（其中 2 次照抄的是修好的版本）|

### 触发证据（产出物级，无歧义）

`OriginalSkill__r2` 的 `report.json` 里，发电机 `123_STEAM_3` 的 commitment 出现
**2.0 / 3.0 / 4.0**（直方图：3.0×31、4.0×3、2.0×2），共 **36** 个越界值。

verifier 的报错正好命中：

```
E  AssertionError: 123_STEAM_3 commitment contains values other than 0/1
   assert False
   /verifier/test_outputs.py:178
```

这与 §机械证明 的预测完全一致：`ub=1` 被 `alloc` 静默丢弃后，
"commitment" 变量不再受上界约束，求解器把它推到 2、3、4 —— 物理上不可能是 0/1 指示量。
该次运行的目标值 776,342 也明显低于其余运行（1.2–5.6M），说明它是在**放松后的空间**里"更便宜"。

### P7 得到验证

**全部 6 次运行都照抄了文档里的 `alloc`**（`uses_alloc = 3/3 + 3/3`）。
这直接证实了 P7 的预测：机制落在**文档里可复制的代码块**时，agent 一定会执行到它 ——
与 01 号（文档示例，被运行时探查化解）和 03 号（`.skill` 实现文件，从不执行）形成鲜明对比。

### 统计上的诚实边界

- 每个 arm 只有 **2 份** report（3 次运行里有 1 次 agent 没能产出报告），样本极小；
  reward 层面三臂全 0，**无法**据此谈 effectiveness。
- 但**产出物级**证据是无歧义的：一个 0/1 字段里出现了 3.0 和 4.0，
  且 verifier 的断言精确点名了该发电机。
- 因此本案例的结论限定为：**不一致性确实被触发并直接导致校验失败**，
  不声称它在 reward 层面造成可测量的差异（该任务本身在地板上）。

---

## 文件

| 文件 | 内容 |
|---|---|
| `builder/prove_alloc.py` | 机械证明（从真实 SKILL.md 抽取 helper，**决定性证据**） |
| `repair/alloc.repaired.py` | 最小修复后的 helper |
| `evidence/prove_output.txt` | 证明输出存档 |
| `evidence/analysis.json` | 6 个 cell 的逐条指标 + 36 个越界值明细 |
| `evidence/uc_alloc_analyze.py` | 轨迹/产物分析脚本 |
