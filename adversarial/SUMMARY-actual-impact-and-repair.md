# 哪些不一致性**确实产生了确定影响**，且 repair **规避了**它

把七个对抗构造 + 轨迹审计 + 十任务三臂对照实验的全部证据放在一起，按「影响是否确定」与「repair 是否规避」两个维度分类。

---

## 结论：**只有 1 个案例两半都成立**（且它是我自己构造的）

| 判定 | 案例数 | 是哪些 |
|---|---|---|
| 影响确定 **且** repair 规避了 | **1** | 04 号 `energy-unit-commitment` |
| 影响确定，但 **repair 从未被测试** | 2 | `latex-formula-extraction`、`pddl-tpp-planning` |
| repair 改变了行为、但影响**不可测量** | 1 | 07 号 `lab-unit-harmonization` |
| **repair 反而制造了失败**（反向） | 1 | 02 号 `grid-dispatch-operator` |
| 从未触发 | 3 | 01、03、06 号 + mario 试点 |

**而在真实跑过的 10 个 repaired skill 集合里，没有任何一个任务出现 RepairedSkill 优于 OriginalSkill。**

---

## A. 影响确定 且 repair 规避了 —— 唯一一条：04 号

**任务**：`energy-unit-commitment`｜**不一致性**：`milp-solver-workflow/SKILL.md`
给出的可复制 helper `alloc(name, shape, lb, ub, integer)` **函数体从不读 lb/ub/integer**，
而紧随其后的调用点写着 `alloc("commitment", (G,T), lb=0, ub=1, integer=True)`。

### 影响（产出物级，无歧义）

| cell | reward | 产出 report | commitment 越界值 |
|---|---|---|---|
| OriginalSkill r1 | 0.0 | ✓ | 0 |
| **OriginalSkill r2** | **0.0** | **✓** | **36** |
| OriginalSkill r3 | 0.0 | ✗ | — |

越界值明细（`ub=1` 被丢弃后 commitment 不再有上界）：

```
123_STEAM_3  hour 41 = 3.0    hour 44 = 4.0    hour 45 = 2.0
121_NUCLEAR_1 hour 17 = 2.0   ...  共 36 个
```

verifier 精确点名：

```
E  AssertionError: 123_STEAM_3 commitment contains values other than 0/1
   /verifier/test_outputs.py:178
```

**6/6 运行都照抄了文档里的 `alloc`** —— 这解释了为什么它会真的被触发。

### repair 规避了它

| 条件 | 产出 report | 其中非二值 | 照抄修好的 helper |
|---|---|---|---|
| OriginalSkill | 2/3 | **1/2** | 0/3 |
| RepairedSkill | 2/3 | **0/2** | 2/3 |

### 诚实边界

每个 arm 只有 **2 份** report（各有 1 次 agent 没产出报告）；两臂 reward 都是 **0.0**
（该任务本身在成功率地板上）。所以这里的"影响"是**校验层**的确定失败，
不是 reward 层可测量的差异。

---

## B. 影响确定，但 **repair 从未被测试** —— 2 条（来自轨迹审计，不在 repaired 集合里）

这两条是全库**影响证据最强**的，可惜 `fixed_skills/` 里没有它们，所以"repair 规避"这半边无数据。

### B1 `latex-formula-extraction`（最强）

- **不一致性**：`marker/SKILL.md` 写 `pdf_to_markdown` 的 `timeout` 默认 **600**，
  实现 `marker_to_markdown.py` 是 **120**。
- **轨迹证据**：`timed out after 120s` **×4**、`timed out after 600s` **×2**。
  agent 先按默认值跑 → 120s 超时；照文档显式传 `--timeout 600` → 又超时。
- **影响**：**3/3 运行 reward=0**；24 次报错 / 88 轮次；**43% 的轮次花在错误—修复循环**（全库最高）。
- 这是唯一一条「文档 → 实现行为 → 运行失败」完整闭环的因果链。

### B2 `pddl-tpp-planning`

- **不一致性**：SKILL.md 演示 `from unified_planning.shortcuts import SequentialPlanValidator`，
  容器里的版本没有这个名字。
- **轨迹证据**：`ImportError: cannot import name 'SequentialPlanValidator'` 全语料 6 次，
  **3/3 运行都中**。
- **影响**：3/3 失败，14 次报错 / 75 轮次，21% 轮次用于恢复。

> 这两条都属于「文档里的可复制代码/参数 → agent 照抄 → 失败」，
> 与我构造的 04 号是同一机制，只是它们所在的任务没进 `fixed_skills/`。

---

## C. repair 改变了行为，但影响**不可测量** —— 07 号

`lab-unit-harmonization`：正文两处承诺 5% 容差并钳制，代码块写死 `NO CLAMPING!`。

| 条件 | 平均 reward | 中位近边界残留 | 写了钳制代码 |
|---|---|---|---|
| OriginalSkill | 0.604 | **169** | **0/3** |
| RepairedSkill | 0.465 | **39** | **3/3** |

repair 确实改变了 agent 的实现（残留 169 → 39），但 reward 反向且 **p=1.000** ——
真正主导失败的是每次 **1–2 万个值根本没做单位换算**，钳制只影响几百个，被淹没。

---

## D. repair **制造**了失败（反向案例）—— 02 号

`grid-dispatch-operator`：原始文档声明支持 MATPOWER Type-1 分段线性成本，而技能与评分器
**都**忽略 `gencost[:,0]`。

- **原版文档的影响是 0**：type1 数据上 3/3 OriginalSkill 运行全部**忽略 MODEL**、
  上报 200、**全部通过**。
- **我的"最小修复"制造了失败**：修复文本显式提到 MODEL 列，促使 2/3 运行去解析它，
  算出**经济上正确**的 5000 → 评分器期望 200 → 失败。type1 上 **1.000 → 0.333**。

这条不属于"repair 规避影响"，而是它的镜像：**当评分器与实现共享同一个误读时，
让文档更严谨会降低测得成功率。**

---

## E. 十任务三臂对照实验：**没有任何一个任务 repair 有提升**

`fixed_skills/`（真实跑过的 10 个 repaired skill）× 3 trial：

| 任务 | NoSkill | Original | Repaired | R−O |
|---|---|---|---|---|
| crystallographic | 0.607 | 0.880 | 0.850 | −0.030 |
| dialogue-parser | 0.500 | 0.833 | 0.722 | −0.111 |
| mario-coin-counting | 0.000 | 0.667 | 0.333 | −0.333 |
| fix-erlang-ssh-cve | 0.333 | 0.333 | 0.333 | 0.000 |
| civ6 / data-to-d3 / energy / fix-druid / grid / court | 0 | 0 | 0 | 0 |

**零个任务出现 Repaired > Original。** 此前审计已给出原因：
9 个任务里只有 4 个真正改了实现文件，其余主体是"把文档写得和代码一致"，
而任务成败取决于模型/流程知识而非文档-代码一致性。

---

## 最终回答

> **在这一整套证据里，只有一个不一致性同时满足「实际使用中产生了确定影响」和
> 「repaired skill 规避了它」—— 04 号的 UC `alloc` helper。**
>
> 它的影响是确定的（36 个 commitment 取到 2/3/4，verifier 精确点名），
> repair 也确定规避了（0/2 vs 1/2，2/3 运行照抄了修好的 helper），
> 但样本只有每臂 2 份 report，且任务在 reward 地板上 —— 结论限定在**校验层**。
>
> 另有两条影响**更确定**的（`latex-formula-extraction` 的 120s/600s 超时、
> `pddl-tpp-planning` 的 ImportError），但它们从来没被 repair 过，所以后半句无从验证。
>
> 而在真正被执行过 repair 的 10 个任务里，**没有任何一个**能指认出一条
> 「不一致性造成确定影响、repair 规避了它」的因果链。
