# 07 · 5% 容差 / 钳制（clamp）—— **机制已触发，但效果被淹没**

**目标不一致性**：`lab-unit-harmonization` 的 `SKILL.md` 内部自相矛盾。

**正文两处承诺钳制**（第 198 行 "Important"、Best Practices 第 4 条）：

> "In these edge cases, it's acceptable to use a **5% tolerance and clamp values slightly
> outside the boundary**." / "Use a **5% tolerance** when checking ranges and **clamp edge
> cases to boundaries**"

**而同一份文档里可复制的代码块明说禁止**（第 180 行）：

```python
    # No conversion worked - return original (NO CLAMPING!)
    return value
```

## 关键事实：出厂数据里这条不一致性**已经是活的**

用 verifier 的 `REFERENCE` 直接扫出厂 `ckd_lab_data.csv`：

```
2590 行；20433 个值落在参考区间外
  其中   423 个在区间外 1-5%（正是文档所说的"edge case"）
        20010 个在区间外 >5%（这些是真的用了别的单位）
```

**不需要任何对抗性数据扰动** —— 423 个近边界值已经在出厂数据里，逼着 agent 做"钳制还是不钳制"的决定。

## 单变量修复（遵守 P8）

只改一处：把那个 `return value  # NO CLAMPING!` 换成兑现正文承诺的钳制分支。

```diff
-    # No conversion worked - return original (NO CLAMPING!)
+    # No conversion worked. The prose below ("Important") and Best Practice 4
+    # both promise a 5% tolerance with clamping to the boundary; honour it here
+    # instead of silently returning an out-of-range value.
+    if max_val is not None and max_val < value <= max_val * 1.05:
+        return max_val
+    if min_val is not None and min_val * 0.95 <= value < min_val:
+        return min_val
     return value
```

diff 只有这一处，没有顺带"让示例更完整"（06 号的坑）。

## 结果：机制触发 ✓，效果不可测 ✗

| cell | reward | 输出行数 | 区间外总数 | **其中 1-5%** | >5% | agent 写了钳制代码 |
|---|---|---|---|---|---|---|
| OriginalSkill r1 | 0.542 | 2548 | 14239 | 169 | 14070 | ✗ |
| OriginalSkill r2 | 0.958 | 2548 | 2788 | **0** | 2788 | ✗ |
| OriginalSkill r3 | 0.312 | 2548 | 21049 | 424 | 20625 | ✗ |
| RepairedSkill r1 | 0.333 | 2548 | 18663 | 396 | 18267 | **✓** |
| RepairedSkill r2 | 0.458 | 2548 | 13405 | 39 | 13366 | **✓** |
| RepairedSkill r3 | 0.604 | 2548 | 9245 | 39 | 9206 | **✓** |

| 条件 | 平均 reward | 中位 1-5% 残留 | 写了钳制代码 |
|---|---|---|---|
| OriginalSkill | 0.604 | **169** | **0/3** |
| RepairedSkill | 0.465 | **39** | **3/3** |

### 机制确实被触发

**3/3 的修复臂运行把钳制代码写进了自己的脚本；0/3 的原臂写了任何钳制逻辑。**
残留的近边界值中位数从 **169 降到 39** —— 修复改变了 agent 的实现，方向与预测一致。

### 但 reward 反向了，而且这个对比没有意义

- reward 是 **0.604 → 0.465**（反向），Mann-Whitney **p = 1.000**（n=3 vs 3，什么都测不出）。
- 真正的原因在 >5% 那一列：**每 6 千到 2 万个值根本没被换算**。
  任务的主要失败模式是"单位换算没做全"，而钳制只影响几百个近边界值 ——
  **信号的量级差了两个数量级，被完全淹没**。

所以本案例的正确读法是：

> **不一致性被触发了，也确实改变了 agent 的行为，
> 但其贡献在 reward 上被任务的主导失败模式淹没，无法测量。**

这与 04 号（触发并直接导致校验失败）形成有用的对照：
**"机制可触发"和"效果可测量"是两件独立的事** ——
前者只需要 agent 照抄到它，后者还需要它在任务的误差预算里占足够大的份额。

## 新增 P9 · 触发 ≠ 可测量

触发判定和效果判定必须分开报：

| 判定 | 需要的证据 | 本案例 |
|---|---|---|
| **是否触发** | agent 的行为因人而异地改变（写了钳制代码；残留值 169 → 39） | ✓ |
| **效果多大** | 该行为在任务误差预算中的份额 | ✗（被 >5% 换算失败淹没） |

如果一个 finding 的影响量级远小于任务本身的噪声/主导失败模式，
即使机制完美触发，**也不该写进 effectiveness 结论**。

## 文件

| 文件 | 内容 |
|---|---|
| `repair/SKILL.original.md` | 原 SKILL.md（正文承诺钳制 / 代码禁止钳制） |
| `repair/SKILL.repaired.md` | 单变量修复后的 SKILL.md |
| `evidence/analysis.json` | 6 个 cell 的逐项指标 |
| `evidence/lab_clamp_analyze.py` | 分析脚本（区间外计数 + 代码片段检测） |
