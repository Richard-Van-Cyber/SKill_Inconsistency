# adv/01 · adaptive-cruise-control —— 抗积分饱和（anti-windup）

**状态**：**已完成四步**（对抗数据 → OriginalSkill 触发验证 → 修复 → RepairedSkill 对比）
**判定**：**L1 ✓ 触发 / L2 ✓ 归因 / L3 ✗ 修复未规避**；另发现一个**任务侧缺陷**使该任务对所有 cell 都不可满分。

---

## 一、被验证的不一致性

`pid-controller/SKILL.md` 给出一段**供 agent 直接复制**的 `compute()`，紧接着一节宣称已实现三种抗饱和方案：

```python
    def compute(self, error, dt):
        # Integral term
        self.integral += error * dt        # ← 无条件积分，无任何抗饱和
        i_term = self.ki * self.integral
```

```markdown
## Anti-Windup
1. **Clamping**: Limit integral term magnitude
2. **Conditional Integration**: Only integrate when not saturated
3. **Back-calculation**: Reduce integral when output is clamped
```

三种方案**一个都没实现**，而任务要求 agent 创建 `pid_controller.py` 并实现该 `compute(error, dt)`。

## 二、① 对抗性任务数据

只改 `sensor_data.csv` 的**前车轨迹**（`data/sensor_data.adv.csv`），
行数 1501、列名、时间 0–150 全部保持。把 verifier 判分的 t=30–60 跟随窗口换成
「切入 → 急刹到 4 m/s → 爬行贴 15 m → 再加速拉开」，逼出负向再正向的 windup 循环。

## 三、② OriginalSkill 触发验证（3 trial，对抗数据）

| cell | reward | rise s | **vmax** | ssErr | speedCtrl | agent 自己写了抗饱和？ |
|---|---|---|---|---|---|---|
| O r1 | 0.0 | 8.00 | 30.60 | 0.15 | ✓ | ✓ |
| **O r2** | **0.0** | 8.00 | **46.76** | 0.94 | **✗** | **✗** |
| O r3 | 0.0 | 16.30 | 29.55 | 0.69 | ✗ | ✓ |

verifier 阈值：`rise < 10 s`、`max(ego_speed) < 31.5`、`|30 − mean(25–30s)| < 0.5`。

### L1 触发 ✓
O r2 的 `vmax = 46.76` → **超调 56%**（阈值 5%），`ssErr = 0.94`（阈值 0.5），
`TestSpeedControl::test_speed_control` FAILED。

### L2 归因 ✓
O r2 产出的 `pid_controller.py`，其 `compute()` 就是文档那段代码的翻版：

```python
def compute(self, error, dt):
    self.integral += error * dt
    derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
    self.prev_error = error
    output = self.kp * error + self.ki * self.integral + self.kd * derivative
    return output
```

标记检测：`self.integral += error * dt` **present**；
`if not saturated` / `max(-` / `min(` / `clamp` **全部 absent** → 零抗饱和。
即：**照抄文档 → 积分跑飞 → 超调 56%**，因果链完整。

## 四、③ 最小修复（单变量）

只改 `compute()` 的积分项一处，实现文档自己列出的第 1、2 两种方案
（conditional integration + integral clamping），其余一字未动。

## 五、④ RepairedSkill 对比（3 trial，同一份对抗数据）

| cell | reward | rise s | vmax | ssErr | speedCtrl | 抗饱和 |
|---|---|---|---|---|---|---|
| R r1 | 0.0 | 8.50 | 31.30 | 0.01 | ✓ | ✓ |
| R r2 | 0.0 | 8.00 | **36.54** | 1.16 | ✗ | ✓ |
| R r3 | 0.0 | n/a | n/a | n/a | ✗ | ✗ |

| 条件 | 平均 reward | speedCtrl 通过 | agent 自写抗饱和 |
|---|---|---|---|
| OriginalSkill | 0.000 | **1/3** | 2/3 |
| RepairedSkill | 0.000 | **1/3** | 2/3 |

### L3 修复未规避 ✗

修复臂与原臂**完全相同**（1/3）。原因很清楚：

- **agent 本来就大概率自己加抗饱和**（原臂 2/3 就加了），所以文档有没有并不改变它是否加；
- 加了也不一定够 —— R r2 的 `pid_controller.py` 里**有**抗饱和，`vmax` 仍然是 **36.54**；
- 反过来 O r1 用的是原版文档却写了 `max(-10.0, min(10.0, self.integral))`（它自己加的），速度环通过。

**结论**：文档里的抗饱和缺失**不是**这条任务的绑定约束。agent 把这段代码当**起点**而不是**成品**。

## 六、附带发现：一个任务侧缺陷，使该任务对所有 cell 都不可满分

六个 cell 里有 **4 个**报同一条断言：

```
E  assert 1.95 >= 5.0        # verifier/test_outputs.py:261  TestSafety::test_safety
```

`1.95` 在两侧、各 arm 完全一致 → 查数据发现**出厂 `sensor_data.csv` 自己就有**：

| t (s) | lead_speed | distance |
|---|---|---|
| 121.4 | 0.00 | 3.97 |
| 121.6 | 1.02 | **1.95** |
| 121.7 | 2.01 | 1.96 |
| 121.9 | 4.02 | 3.15 |

出厂数据在 t≈121.4–121.9 有一段 **1.95 m 的车距**，而 verifier 断言 `min_d >= 5.0`。
**这条检查在出厂数据上就不可通过，与 skill 无关。**

这说明：ACC 任务 0% 的基线**至少部分来自这个任务侧缺陷**；
它在我两臂之间是**常量**，因此不污染 O/R 对比，但把所有人的 reward 上限压到 1.0 以下。

## 七、任务 01 的最终判决

| 层 | 判定 | 依据 |
|---|---|---|
| **L1 触发** | **✓** | O r2：vmax 46.76（超调 56%），speedCtrl FAILED |
| **L2 归因** | **✓** | O r2 的 `compute()` 零抗饱和，与文档代码一致 |
| **L3 修复规避** | **✗** | 修复臂 1/3 = 原臂 1/3；且有抗饱和的运行也超调 36.54 |

**两条新教训（加入协议）**：

> **P10 · 修复只有在该不一致性是"绑定约束"时才有效。**
> agent 会把文档里的代码当起点改写；如果它本来就会自行补上被修复的东西，
> 改文档不会移动结果。判断办法：先数**原臂里有多少运行已经自己规避了这个缺陷**
> （本例 2/3 自行加了抗饱和）—— 比例高就说明不是绑定约束，修复收益必然接近 0。

> **P11 · 构造对抗数据前必须先验证任务本身可满分。**
> 本例的对抗 profile 尚未成为瓶颈，出厂数据里的 1.95 m 车距就已经让 `test_safety` 不可能通过。
> 正确做法：先用参考解跑一遍出厂数据，确认能得 1.0，再动手加扰动。

## 八、若要继续推进本任务

需要**两个**数据变体：

1. `sensor_data.feasible.csv`：把 t=121.4–121.9 的车距抬到 ≥6 m，让 `test_safety` 可通过
   —— 这是**修任务**，不是修 skill；
2. 在 1 的基础上再加急刹事件 → 真正干净的对抗数据。

然后重跑 2×3，此时 reward 才可能区分两臂。

## 文件

| 文件 | 内容 |
|---|---|
| `data/sensor_data.adv.csv` | 对抗性前车轨迹（1501 行，schema 与出厂一致） |
| `repair/pid-controller.SKILL.original.md` / `.repaired.md` | 修复 diff 两侧 |
| `evidence/prove_windup.py` / `prove_output.txt` | 机械证明（4 组增益 × 2 变体，全部一致） |
| `evidence/check_feasibility.py` | 出厂/对抗数据的车距下界检查（发现 1.95 m 缺陷） |
| `evidence/experiment.txt` / `analysis.json` | 6 个 cell 的逐项指标与判定 |
| 服务器 | `experiments/adv01-acc-20260924/` |
