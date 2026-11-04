# 03 · 未声明的副作用（undeclared side effect）—— 构造正确，但**未被触发**

**目标不一致性**：`pddl-tpp-planning` 的 `save_plan.skill`

```python
def skill(plan, path):
    with open(path, "w") as f:                       # 先写文本计划
        for action in plan.actions:
            f.write(str(action) + "\n")
    with open(path.replace('.txt', '.pkl'), "wb") as f:   # ← 若无 .txt，这是同一个文件
        pickle.dump(plan, f)
    return path
```

当 `path` 不含 `.txt` 时，`path.replace('.txt','.pkl')` **等于 `path`**，
于是同一个文件被以二进制重新打开并覆盖 —— **刚写好的文本计划被 pickle 字节销毁**。
即使 `path` 以 `.txt` 结尾，也会额外产生一个文档从未声明的 `.pkl` 文件。

任务 verifier 自己的注释写着 *"no reference pickle is required"* —— 这个写入纯属多余。

---

## 一、机械证明（0 次模型调用、0 次容器）

`builder/prove_overwrite.py` 的输出：

```
task01.txt    60 bytes  TEXT plan (ok)
task01.plan  117 bytes  BINARY pickle — text plan DESTROYED
task01       117 bytes  BINARY pickle — text plan DESTROYED
extra files created: ['task01.pkl']
```

满足三个必要条件：

| 条件 | 本案例 |
|---|---|
| **C1 数据依赖** | 出厂 `problem.json` 的 `plan_output` 全是 `taskNN.txt` → bug 休眠 |
| **C2 静默** | 不抛异常；文件存在、名字正确，只有**内容**是二进制 |
| **C3 不可探知** | 从 `problem.json` / `task.md` 看不出；必须读 `.skill` 源码才会发现 |

## 二、对抗数据

只把 `problem.json` 的 `plan_output` 从 `taskNN.txt` 改成 `taskNN.plan`。
task.md 只说"write the generated plan to the path specified by plan_output"，
扩展名完全任意 → **语义等价**（唯一的例外是它恰好决定了 bug 是否触发，这正是目的）。

## 三、最小修复

删掉那 3 行 pickle 写入（见 `repair/save_plan.repaired.skill`）。
verifier 明确说不需要 pickle，所以这是纯删除。

## 四、配对实验结果（各 3 trial）—— **未触发**

| 数据变体 | OriginalSkill | RepairedSkill |
|---|---|---|
| `.txt`（对照） | 1.000 | 0.667 |
| `.plan`（对抗） | 0.667 | 1.000 |

**判定为未触发**，证据：

1. **verifier 从未报解码错误。** 如果计划文件是 pickle，
   `verifier/test_outputs.py` 的 `with open(plan_file) as f:`（文本模式）会抛 `UnicodeDecodeError`。
   实际失败原因是 `AssertionError: Plan error in task task01`（**计划内容不合法**）
   与 `Missing output file: task14.txt`（**agent 没写全输出**）—— 都与该 finding 无关。
2. **轨迹里 `pickle` / `.pkl` 出现 0 次。** agent 读到过 `save_plan.skill`（有 Read），
   但没有任何一次真的调用 skill 的保存路径 —— 它们**自己写脚本把计划落盘**。

## 五、这是第四个"机制成立但运行不触发"的案例，原因是同一个

到现在为止四个构造的结论是一致的：

| # | 任务 | 机制是否成立 | agent 运行时是否触发 | 原因 |
|---|---|---|---|---|
| 01 | earthquake 字段名遮蔽 | ✓ | ✗ | agent 先探 schema 再写代码 |
| 02 | grid Type-1 格式误读 | ✓（25× 差距）| **✓（在"修复"臂上）** | 修复文本促使 agent 去解析 MODEL |
| 03 | pddl save-plan 覆盖 | ✓（机器证明）| ✗ | agent 不执行 skill 的代码，自己实现 |
| 04 | mario dedup/grayscale | 机制本身正确 | ✗ | 按 SKILL.md 参数跑就是对的 |

**共同根因（新增原则 P7）**：
**agent 把 skill 当作"文档"读，而不是当作"代码"执行。**
它们读 `SKILL.md` 了解流程，然后用自己写的脚本实现该流程。
所以——

- 藏在 **`.skill` / `scripts/` 实现文件**里的 bug（03）永远不会执行；
- 藏在**文档与数据 schema 不一致**里的问题（01）会被运行时探查化解；
- 只有**文档主动改变了 agent 的实现选择**的那种不一致性（02 的修复文本）才会生效。

**这直接决定了构造策略**：要让不一致性触发，扰动必须落在
**agent 会照抄的那份文本**（`SKILL.md` 的流程/公式/参数），
而不是落在它不会执行的脚本实现里。

---

## 六、文件

| 文件 | 内容 |
|---|---|
| `data/problem.shipped.json` | 出厂（`plan_output = taskNN.txt`，bug 休眠） |
| `data/problem.adv.json` | 对抗（`plan_output = taskNN.plan`，bug 激活） |
| `repair/save_plan.original.skill` | 原始实现 |
| `repair/save_plan.repaired.skill` | 最小修复（删掉未声明的 pickle 写入） |
| `builder/prove_overwrite.py` | 机械证明：文本被二进制覆盖（**决定性证据**） |
| `evidence/pddl_planpath_analyze.py` | 轨迹/产物分析脚本 |

## 七、运维记录：Docker 地址池耗尽

本案例的对照组首次全部 `environment_error`：
`failed to create network ...: all predefined address pools have been fully subnetted`。

原因是我此前三个 study 的 **59 个已退出容器**仍持有 **29 个网络**。
清理方式（**只删 `anonymous/*` 镜像的容器与我自己的网络前缀**，不碰其他用户的服务）：

```bash
for c in $(docker ps -aq --filter status=exited); do
  img=$(docker inspect -f '{{.Config.Image}}' $c)
  case "$img" in anonymous/*) docker rm -f "$c";; esac
done
for net in $(docker network ls --format '{{.Name}}' | grep -E '^project-(eqadv|gadv|pddladv|h45|dr)-'); do
  docker network rm "$net"
done
```

清理后网络数 33 → 4，对照组重跑即恢复正常。
