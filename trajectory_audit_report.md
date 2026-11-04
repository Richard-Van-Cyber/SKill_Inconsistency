# Skill 不一致性对执行轨迹的实际影响审计报告

- **审计日期**：2026-09-17
- **轨迹来源**：`originalskill-traces-20260916/readable/`
- **覆盖轨迹**：31 条（10 任务 × 最多 3 模型）
- **对照来源**：`tool_audit_result/` 中的 10 份不一致性报告

---

## 一、全局得分与失败概览

| 任务 | 模型 | 得分 | 结果 | 不一致性实际触发 |
|---|---|---|---|---|
| civ6-adjacency-optimizer | claude-haiku (01) | 0.25 | 部分成功 | F-003 直接触发 |
| civ6-adjacency-optimizer | claude-opus (02) | 0.90 | 成功 | 均绕过 |
| civ6-adjacency-optimizer | codex-gpt55 (02) | 0.00 | 失败 | F-003+F-004 连锁 |
| data-to-d3 | claude-haiku (01) | 0.00 | 失败 | F-002+F-005+F-007+F-008 |
| data-to-d3 | claude-opus (02) | 0.00 | 失败 | F-002+F-005+F-007+F-008 |
| data-to-d3 | codex-gpt55 (02) | 0.00 | 失败 | F-002+F-007+F-008 |
| dialogue-parser | claude-haiku (02) | 0.833 | 成功 | 均绕过（自主实现） |
| dialogue-parser | claude-opus (02) | 0.667 | 部分成功 | F-002 软触发 |
| dialogue-parser | codex-gpt55 (02) | 0.833 | 成功 | 已识别主动绕过 |
| energy-market-pricing | claude-haiku (02) | 0.00 | 失败 | F-001+F-008+F-009 连锁 |
| energy-market-pricing | claude-opus (02) | 1.00 | 成功 | 绕过（手工实现） |
| energy-market-pricing | codex-gpt55 (02) | — | — | — |
| grid-dispatch-operator | claude-haiku (02) | 0.00 | 失败 | F-004 维度冲突 |
| grid-dispatch-operator | claude-opus (01) | 1.00 | 成功 | 均绕过 |
| grid-dispatch-operator | codex-gpt55 (01) | 1.00 | 成功 | 均绕过 |
| mario-coin-counting | claude-opus (01) | 0.00 | 失败 | F-001+F-005 触发调试循环 |
| mario-coin-counting | claude-haiku (02) | 1.00 | 成功 | F-001 警告级触发 |
| mario-coin-counting | codex-gpt55 (02) | 1.00 | 成功 | F-001 警告级触发 |
| court-form-filling | claude-haiku (02) | 0.00 | 失败 | F-001+F-004+F-005/006 |
| court-form-filling | claude-opus (02) | 1.00 | 成功 | 均处理 |
| court-form-filling | codex-gpt55 (02) | 1.00 | 成功 | 均处理 |
| crystallographic-wyckoff | claude-haiku (02) | 1.00 | 成功 | F-001 被文档明确防御 |
| crystallographic-wyckoff | claude-opus (02) | 1.00 | 成功 | F-001 被文档明确防御 |
| crystallographic-wyckoff | codex-gpt55 (02) | 1.00 | 成功 | F-001 被文档明确防御 |
| fix-druid-loophole-cve | claude-opus (01) | 0.00 | 失败 | API 预算耗尽（掩盖不一致性） |
| fix-druid-loophole-cve | claude-haiku (02) | 0.00 | 失败 | API 预算耗尽 |
| fix-druid-loophole-cve | codex-gpt55 (02) | 0.00 | 失败 | API 预算耗尽 |
| fix-erlang-ssh-cve | claude-opus (01) | 0.00 | 失败 | skills 未调用 |
| fix-erlang-ssh-cve | claude-haiku (02) | 0.00 | 失败 | API 预算耗尽 |
| fix-erlang-ssh-cve | codex-gpt55 (01) | — | 流中断 | F-007 触发后流断 |
| fix-erlang-ssh-cve | codex-gpt55 (03-retry) | 1.00 | 成功 | 不依赖 skill 直接修复 |

---

## 二、不一致性触发矩阵（跨轨迹）

对每条 Finding，标注其在实际轨迹中的状态：**✓触发** / **⚠软触发** / **○绕过** / **✗未到达**

| Finding | 严重度 | 任务 | haiku | opus | codex | 实际后果 |
|---|---|---|---|---|---|---|
| F-003 模块路径 `hex_utils` vs `src.hex_utils` | Critical | civ6 | ✓ 直接触发 | ○ 环境路径自动解析 | ✓ 间接混乱 | haiku 得分 0.25；codex 失败 |
| F-005 Edge序列化 `from/to` vs `source/target` | Critical | dialogue | ○ 自主实现绕过 | ○ 自主实现绕过 | ⚠ 识别后绕过 | 无实际损失（绕过成本~0）|
| F-006 from_dict 键名矛盾 | Critical | dialogue | ○ 未调用 | ○ 未调用 | ○ 未调用 | 未触发 |
| F-001 Wyckoff 提取方法矛盾 | Critical | wyckoff | ○ 文档有明确指导 | ○ 文档有明确指导 | ○ 文档有明确指导 | 完全防御，3/3 成功 |
| F-001 CLARABEL 版本依赖 | High | energy-market | ✓ 触发→环境混乱 | ⚠ 触发但修复 | — | haiku 失败；opus 额外~10步 |
| F-004 limit_MW vs rating_MW | High | grid-dispatch | ✓ 维度错误→失败 | ○ 手工绕过 | ○ 手工绕过 | haiku 失败 |
| F-008 balance_constraints 归属 | High | energy-market | ✓ 模型定义混淆→失败 | ⚠ 手工修复 | — | haiku 失败 |
| F-009 reserve_con 归属 | High | energy-market | ✓ 同上 | ⚠ 手工修复 | — | haiku 失败 |
| F-007 SecurityConfig.java 双写 | High | fix-druid | ✗ API预算先耗尽 | ✗ 同 | ✗ 同 | 被掩盖 |
| F-007 senior-security 空实现 | High | fix-erlang | ✗ API预算先耗尽 | ✗ skill未调用 | ✓ 调用后流中断 | 被掩盖/直接中断 |
| F-001 FFmpeg -vsync 弃用 | High | mario | ⚠ 警告级 | ✓ 触发调试循环 | ⚠ 警告级 | opus 失败（循环~32步） |
| F-002 ImageMagick convert→magick | High | mario | ✗ 未调用 | ✗ 未调用 | ✗ 未调用 | 未触发 |
| F-004 cv2/numpy 依赖未声明 | High | mario | ○ 环境已有 | ✓ 触发冗余步骤 | ○ 环境已有 | |
| F-005 彩色→灰度冗余转换 | High | mario | ○ | ✓ 冗余步骤 | ○ | |
| F-002 力导向确定性 | High | data-to-d3 | ✓ 影响最终输出 | ✓ 影响最终输出 | ✓ 影响最终输出 | 3/3 失败 |
| F-005 D3 v6 vs v7 | High | data-to-d3 | ✓ 下载 v6 | ✓ 提取 v6 | ✓ 验证混淆 | 贡献失败 |
| F-007 跨文件函数接口 | High | data-to-d3 | ✓ 实现但无规范 | ✓ 同 | ✓ 同 | 3/3 失败 |
| F-008 输出格式未声明 | High | data-to-d3 | ✓ | ✓ | ✓ DOM验证失败 | 3/3 失败 |
| F-001/004/005 court-form | High | court-form | ✓ 触发→失败 | ○ 处理 | ○ 处理 | haiku 失败 |
| F-004 calculate_total_adjacency 签名 | High | civ6 | ✓ 静默简化 | ✓ 深入理解 | ✓ 触发KeyboardInterrupt | 质量差异显著 |

---

## 三、逐任务深度分析

### 3.1 civ6-adjacency-optimizer
**核心结论：F-003 是分水岭，F-004 决定质量上限**

**haiku（0.25分）**
F-003 在第 0117 步触发 `ModuleNotFoundError: No module named 'hex_grid_spatial'`。Agent 被迫放弃 skill 模块，改用手写 SQL 查询替代，绕道成本约 **13–15 步**。最终因使用简化的邻接算法，`total_adjacency: 5`（最优解为 18），质量损失 **72%**。

**opus（0.90分）**
运行环境中 `/home/agent/.claude/skills/` 路径使裸导入 `hex_utils` 自动可寻址，F-003 未触发。Agent 深入理解了 adjacency_rules.py 的真实行为，正确计算出 `CAMPUS +7 / IZ +7 / CH +4`，总分 18。额外步骤：**0 步**。

**codex-gpt55（0.00分）**
F-003 路径混乱与 F-004 签名不符叠加，导致 `apply_destruction()` 调用链中两次触发 `KeyboardInterrupt`，搜索空间无法退出。最终因 API 速率限制（429）彻底失败。全部步骤浪费。

**关键引用**（haiku 第 0117 步）：
```
ModuleNotFoundError: No module named 'hex_grid_spatial'
→ Agent 绕道：用 sqlite3 直接查询 MAP 文件，丢失 adjacency 精度
```

---

### 3.2 data-to-d3
**核心结论：4 个 High 级 Finding 联合阻断，3/3 模型全部得 0**

F-002（力导向非确定性）、F-005（D3 版本歧义）、F-007（跨文件函数接口未声明）、F-008（输出格式未规范）在三个模型上全部触发，且互相叠加：

- Agent 按文档 description 的 v6 下载/提取 D3，但 vendor 路径是 v7，API breaking change 导致可视化静默出错
- 力导向没有固定 tick 数，每次运行布局不同，评估器无法验证一致性
- `highlightTableRow`/`highlightBubble` 等跨文件联动函数在 SKILL.md 中无接口声明，Agent 各自实现但无统一规范
- codex 的 DOM 验证：期望 6 个 legend 但数据实际只有 5 个 sector，出错退出码 1

**关键引用**（codex 第 1032 步）：
```
if (bubbles !== 50 || rows !== 50 || legends !== 6 || selectedRows !== 1)
→ exit 1 （实际数据只有5个sector，文档未说明）
```

**token 浪费**：haiku 18 turns/164s，opus 21 turns/198s，codex 单 turn 消耗 293k input tokens。

---

### 3.3 dialogue-parser
**核心结论：Critical 级别的序列化键名冲突（F-005/F-006）实际未触发——因为所有 Agent 都主动绕过了 skill**

3 个模型全部识别出 skill 文档与任务格式要求之间的张力，选择完全自主实现 `parse_script()`，从未调用 `Edge.to_dict()` 或 `from_dict()`。

- haiku/codex（0.833）：完全自主实现，规避所有 Finding，验证通过
- opus（0.667）：自主实现但存在节点 ID 生成逻辑 bug（与不一致性无直接关系），导致 53 条 "Edge target does not exist" 错误未被正确处理

**codex 识别证据**（第 515 步）：
```
"The graph helper is present under the skill's scripts directory, not installed 
on PYTHONPATH, so I'll import it by path if useful... I'm adding a standalone 
parser rather than depending on the helper module."
```

**结论**：F-005/F-006 虽为 Critical，但在实际执行中被所有 Agent 规避，零实际伤害。这揭示了一个反直觉现象：**审计发现的"最严重"问题，反而因其显眼性而最容易被 Agent 绕过**。

---

### 3.4 energy-market-pricing
**核心结论：F-001+F-008+F-009 三个 High 级问题连锁触发，haiku 完全失败**

**haiku（0.00分）**
1. F-001：`import cvxpy` 失败 → pip install 失败（`externally-managed-environment`）→ 创建 venv → venv 中 CLARABEL 不存在 → 换用 SCS → CVXPY 矩阵乘法弃用警告大量出现
2. F-008+F-009：`balance_constraints` 在 economic-dispatch 文档中不提，在 LMP 文档中重新定义，haiku 两份文档都遵循，模型定义产生歧义 → 优化器状态 `optimal_inaccurate`
3. 最终因修改 solver 状态判断逻辑仍无法解决，得分 0

token 浪费：**~160K tokens**，大量消耗在环境安装失败循环上。

**opus（1.00分）**
遇到同样的 CLARABEL 问题，但在创建 venv 后主动设置 `max_iters=10000` 并放宽 `optimal_inaccurate` 状态判定，成功输出：`Cost Reduction $1,899.41`。额外步骤约 **10 步**。

**关键引用**（haiku 轨迹）：
```
ModuleNotFoundError: No module named 'numpy'
→ pip install fails: externally-managed-environment
→ python3 -m venv /root/venv
→ CVXPY: "Using * for matrix multiplication has been deprecated since CVXPY 1.1"
→ ValueError: Optimization failed with status: optimal_inaccurate
```

---

### 3.5 grid-dispatch-operator
**核心结论：F-004（limit_MW vs rating_MW）直接导致 haiku 失败**

**haiku（0.00分）**
按 SKILL.md 文档构造约束矩阵，数据维度为 2869 条支路 vs 510 台发电机，导致：
```
ValueError: Incompatible dimensions (1, 2869) (510, 1)
```
haiku 反复尝试修复维度问题（约 **32 turns**），最终超时失败。

**opus/codex（1.00分）**
两者均手工编写 Python 求解器，不直接依赖 skill 文档中的约束示例，绕过了维度冲突。

**结论**：F-004 的字段命名不一致（`limit_MW` vs `rating_MW`）是表象，更深层的问题是 SKILL.md 中的约束构造示例与真实网络数据规模不匹配，直接影响中小模型的执行稳定性。

---

### 3.6 mario-coin-counting
**核心结论：F-001（FFmpeg 弃用警告）触发调试循环，claude-opus 失败；haiku/codex 高效规避**

**opus（0.00分）**
`-vsync vfr` 产生弃用警告后，Agent 陷入对 `threshold` 和 `dedup_min_dist` 参数的反复调试循环（超过 **32 turns**），根本原因是 SKILL.md 对这两个参数缺乏指导。F-005（彩色→灰度冗余）也触发了冗余处理步骤。最终无法通过验证，得分 0。

**haiku/codex（1.00分）**
同样收到 FFmpeg 弃用警告，但快速跳过，分别在 16 turns 和更少 turns 内完成。

---

### 3.7 court-form-filling
**核心结论：haiku 失败，opus/codex 成功——差异来自文档理解深度**

**haiku（0.00分）**
F-001（副作用声明冲突）、F-004（pypdf 依赖未声明）、F-005/006（dpi 限制未说明）联合触发。Agent 在理解 `forms.md` 工作流时遭遇文档缺失，无法正确完成坐标定位，生成了 `filled.pdf` 但通过验证得分为 0。

**opus/codex（1.00分）**
均成功填充所有字段（Plaintiff/Defendant/Amount/Dates），具体路径更稳健，对文档缺陷有更强的容错能力。

---

### 3.8 crystallographic-wyckoff
**核心结论：F-001（Critical）被 SKILL.md 内置的"反例警告"完全防御，3/3 成功**

这是唯一一个 Critical 级 Finding 被**文档本身明确防御**的案例。SKILL.md 中直接写明：
```
# Wrong approach (do NOT use):
structure.get_symmetrized_structure().wyckoff_symbols  ← 禁止

# Correct approach:
SpacegroupAnalyzer(structure).get_symmetry_dataset().wyckoffs  ← 推荐
```
三个模型全部遵循这一指导，均得 1.00 分，无一失败。

**结论**：这个案例证明，Critical 级别的实现矛盾**可以通过文档内的明确警告完全消除影响**，是唯一成功的防御模式。

---

### 3.9 fix-druid-loophole-cve / fix-erlang-ssh-cve
**核心结论：API 预算耗尽掩盖了 skill 不一致性的实际影响**

几乎所有 druid/erlang 轨迹都因 429 `Experiment API budget reached` 失败，F-007（SecurityConfig 双写覆盖）、F-007（senior-security 空实现）等关键 Finding **未能在失败前被触发**。

唯一例外是 **fix-erlang codex-gpt55 第三次 retry（得分 1.00）**：该 Agent 完全不依赖 `senior-security` skill，直接通过阅读 `ssh_connection_handler.erl` 源码定位认证边界缺陷，添加 `when ?CONNECTED(StateName)` 守卫，成功完成修复。

**关键引用**（codex retry 轨迹）：
```
直接识别 ssh_connection_handler.erl 中的认证边界缺陷
→ 添加 when ?CONNECTED(StateName) 连接状态守卫
→ 阻止未认证消息处理
→ 得分 1.00
```

---

## 四、核心发现

### 发现一：模型规模是不一致性"防弹衣"的关键变量

大模型（opus/codex）普遍采用"读文档+自主实现"策略，不直接依赖 skill 的脚本输出，因此即使不一致性客观存在，也很少被触发。小模型（haiku）倾向于直接照搬文档示例，当文档与实现矛盾时脆弱性显著更高。

| 模型 | 总失败次数 | 因 skill 不一致失败 | 因其他原因失败 |
|---|---|---|---|
| claude-haiku | 7 | **5**（civ6/energy/grid/mario/court） | 2 |
| claude-opus | 4 | 1（data-to-d3） | 3（API/预算） |
| codex-gpt55 | 5 | 1（civ6） | 4（API/预算） |

### 发现二：最高严重级别 ≠ 最高实际伤害

| Finding | 声明严重度 | 实际触发率 | 实际影响 |
|---|---|---|---|
| F-005/F-006 dialogue 序列化键名 | Critical | 0/3（全部绕过） | 零伤害 |
| F-001 wyckoff 提取方法矛盾 | Critical | 0/3（文档防御） | 零伤害 |
| F-003 civ6 模块路径 | Critical | 2/3 | 1 次直接失败，1 次得分 0.25 |
| F-002/F-007/F-008 data-to-d3 确定性 | High | 3/3 | **3/3 全部失败** |
| F-001+F-008+F-009 energy-market | High | 1/2（haiku） | **完全失败 + 160K token 浪费** |

结论：**High 级别的多点联合触发比单个 Critical 更致命**。

### 发现三：静默错误比阻断错误更难发现但影响更深远

data-to-d3 的失败不是因为代码崩溃，而是因为：
- 力导向每次运行布局不同（静默破坏可复现性）
- D3 版本 API 差异导致可视化行为细微出错
- 验证器无法通过 DOM 检查

这类"看似运行成功但结果错误"的静默错误，在实际 Agent 任务中比 `ModuleNotFoundError` 更难诊断。

### 发现四：文档内置"反例警告"是唯一被验证有效的防御模式

wyckoff 任务的 SKILL.md 直接写出了"错误做法"和"正确做法"，3/3 模型全部成功。这是唯一一个通过文档本身完全消除 Critical 级 Finding 影响的案例，值得作为 skill 编写规范推广。

### 发现五：API 预算问题掩盖了 CVE 修复任务中 skill 不一致性的真实影响

fix-druid 和 fix-erlang 的大部分失败是 infrastructure 问题（429）而非 skill 不一致性。但从成功轨迹（erlang codex retry）可以推断：**成功的关键是绕过 skill 直接读代码**。这意味着如果 senior-security 的空实现（F-007）被触发，它将提供虚假的"零 findings"结果，对 Agent 造成错误置信——这个风险在当前轨迹中仅有间接证据。

---

## 五、Token 与步骤浪费量化

| 任务 | 轨迹 | 估计浪费 token | 浪费步骤 | 根本原因 Finding |
|---|---|---|---|---|
| energy-market-pricing | haiku | **~160K** | ~40 步 | F-001+F-008+F-009 |
| civ6-adjacency-optimizer | codex | 全部（失败） | 全部 | F-003+F-004 |
| mario-coin-counting | opus | ~12K | ~32 步 | F-001+F-005 |
| grid-dispatch-operator | haiku | ~8K | ~32 步 | F-004 |
| court-form-filling | haiku | ~10K | ~30 步 | F-001+F-004 |
| data-to-d3 | opus | ~15K | 21 步 | F-002+F-005+F-007+F-008 |
| civ6-adjacency-optimizer | haiku | ~5K | ~15 步 | F-003 |

---

## 六、修复优先级（基于实际轨迹影响重排）

与原审计报告相比，基于实际轨迹重新排序：

| 优先级 | Finding | 实际触发次数 | 实际影响 | 推荐修复 |
|---|---|---|---|---|
| **P0** | data-to-d3 F-002/F-007/F-008（确定性+输出规范） | 3/3 | **3 轨迹全部得 0** | SKILL.md 中明确声明所有输出文件格式；force simulation 必须固定 tick；跨文件函数接口必须文档化 |
| **P0** | energy-market F-001+F-008+F-009（CLARABEL+constraints归属） | 2/2 有效轨迹中 1 失败 | **160K token 浪费 + 完全失败** | 声明 `cvxpy>=1.3.0`；在 economic-dispatch 文档中明确写入"存储 balance_constraints 供 LMP 使用" |
| **P0** | civ6 F-003（模块路径冲突） | 2/3 | **1 得分 0、1 得分 0.25** | 统一导入路径，添加路径配置说明 |
| **P1** | mario F-001（FFmpeg 弃用） | 3/3（严重程度各异） | opus 因此触发调试循环失败 | 更新命令为 `-fps_mode vfr`；补充阈值参数文档 |
| **P1** | grid-dispatch F-004（limit_MW vs rating_MW） | 1/3 | haiku 完全失败 | 统一字段名为 `rating_MW` |
| **P2** | civ6 F-004（calculate_total_adjacency 签名） | 3/3（影响程度各异） | 质量差异 0→18 | 补充签名文档和完整示例 |
| **P2** | erlang F-007（senior-security 空实现） | 间接（API 掩盖） | 潜在错误置信 | 文档明确标注"占位符/待实现" |
| **P3** | dialogue F-005/F-006（序列化键名） | 0/3（全部绕过） | 实际零影响 | 统一为 `source`/`target`（修复成本低，防御未来使用） |

---

## 七、总结

**31 条轨迹中，有 17 条失败（得分 = 0）**，其中：
- **约 8 条**（47% 的失败）与 skill 不一致性直接相关
- **约 5 条**因 API 预算/infrastructure 限制失败（掩盖了 skill 问题）
- **约 4 条**因其他因素失败

最具破坏力的不是单个 Critical 级别的问题，而是 **data-to-d3 的 4 个 High 级 Finding 联合触发**——在 3 个不同模型上全部导致得分 0，是本次审计中唯一"模型无关"的失败模式，也是最需要优先修复的问题集群。

---

*报告生成时间：2026-09-17*
