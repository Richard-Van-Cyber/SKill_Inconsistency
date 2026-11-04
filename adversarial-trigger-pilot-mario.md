# 对抗性触发实验 · 试点：mario-coin-counting

**目的**：不靠推断，直接在真实任务镜像里**执行**，判定 `mario-coin-counting` 的 5 条已审计不一致性
到底有没有被触发、能不能被对抗性数据触发。

**方法**：全机械、无 LLM。在服务器 `10.0.0.64` 的真实任务镜像
`anonymous/mario-coin-counting:9d7ba40d718d` 里，逐条复现每个 finding 的触发条件。

**一句话结论**：**5 条 finding 全部未被触发（0/5）**；skill 在出厂数据上是功能正确的
（按 SKILL.md 推荐参数计数，8/8 帧与 ground truth 完全一致）。这 5 条都是「条件式潜在风险」，
触发条件在本环境里**不成立**。

---

## 1. 环境事实（实测）

| 项 | 实测值 | 说明 |
|---|---|---|
| ffmpeg | **6.1.1-3ubuntu5** | 不是 7.x |
| ImageMagick | **6.9.12-98**（legacy） | `convert` 存在；`magick` 不存在 |
| OpenCV | 4.12.0 | 已预装 |
| 关键帧数 | 8（两种抽取方法都是 8） | 与 ground truth 行数一致 |

---

## 2. 逐条判定

### F-001 `image-editing/SKILL.md` — `convert` vs `magick`（IM7）→ **未触发**

- 触发条件：环境为 ImageMagick 7 且未启用 legacy 兼容工具，`convert` 不存在。
- 实测：`convert --version` = `ImageMagick 6.9.12-98 Q16`，`convert` 正常可用。
- **条件不成立。**

### F-002 `object-counter` — SKILL.md 未声明 cv2/numpy 依赖 → **未触发**

- 触发条件：环境未预装 `opencv-python`/`numpy`，脚本在 `import cv2` 处 `ModuleNotFoundError`。
- 实测：镜像内 `cv2 4.12.0`、`numpy 2.2.6`，可直接 import。
- 文档确实漏写了依赖，但**环境已满足**，所以不产生任何失败。

### F-003 `ffmpeg-keyframe-extraction/SKILL.md` — `-vsync vfr` 在 ffmpeg 7 被移除 → **未触发**

- 触发条件：ffmpeg ≥ 7.0，`-vsync` 被移除 → `Unrecognized option`。
- 实测：ffmpeg 6.1.1，`-vsync vfr` **exit=0**，只打印 `-vsync is deprecated. Use -fps_mode` 警告。
- **条件不成立**（这条 finding 本身写的是条件式："若为 FFmpeg 7.0 及以上"，条件为假）。

### F-004 `image-editing/SKILL.md` — cosmetic → 跳过（`impact_class=cosmetic`）

### F-005 `object-counter/SKILL.md` — `--dedup_min_dist` 文档写"good default value is 3"，
实现是 `required=True` 无默认值 → **条件存在但未被触发**

- 触发条件：agent 按文档措辞**省略** `--dedup_min_dist` → argparse 直接报错退出。
- 实测：该参数确实 `required=True`；但 SKILL.md 给出的示例命令**包含**了该 flag，
  照抄示例就不会踩到。属于「触发条件是 agent 的省略行为，不是数据」。

---

## 3. skill 功能正确性验证（这是本次最重要的读数）

在镜像里完整复现任务流程，使用 **SKILL.md 推荐的参数**（`--threshold 0.9 --dedup_min_dist 3`）：

```
ffmpeg -skip_frame nokey -i /root/super-mario.mp4 -vsync vfr /root/keyframes_%03d.png   -> 8 帧
convert <frame> -colorspace Gray <frame>                                                 -> 2D 灰度，PASS
count_objects(frame, coin/enemy/turtle, threshold=0.9, dedup_min_dist=3)
```

结果与出厂 `verifier/expected_output.csv` 对比：

| frame | ground truth (c/e/t) | skill 输出 (c/e/t) | |
|---|---|---|---|
| 001 | 0/0/0 | 0/0/0 | ✓ |
| 002 | 2/2/0 | 2/2/0 | ✓ |
| 003 | 0/0/0 | 0/0/0 | ✓ |
| 004 | 0/0/0 | 0/0/0 | ✓ |
| 005 | 4/0/1 | 4/0/1 | ✓ |
| 006 | 1/0/0 | 1/0/0 | ✓ |
| 007 | 0/0/1 | 0/0/1 | ✓ |
| 008 | 0/0/1 | 0/0/1 | ✓ |

**8/8 完全一致。** 也就是说：**mario 任务在出厂数据上，只要 agent 照 SKILL.md 做，就一定满分。**
之前三次实验里 RepairedSkill 的失败**不能归因于 `object-counter` 的参数推荐**。

### 3.1 附加：合成图像的参数敏感性（我控制了真值）

用 `coin.png`（35×42）合成已知数量的帧，测 `count_objects` 的行为：

| 场景 | 真值 | dedup=3（SKILL 推荐） | dedup=40 | threshold=0.7 |
|---|---|---|---|---|
| 1 枚 | 1 | 1 ✓ | 1 | 2 ✗ |
| 2 枚，间距 35px | 2 | 2 ✓ | 1 ✗ | 4 ✗ |
| 5 枚，间距 35px | 5 | 5 ✓ | 3 ✗ | 10 ✗ |
| 10 枚，间距 70px | 10 | 10 ✓ | 10 | 20 ✗ |

- **推荐参数在「物体互不重叠」时完全正确**，无论 1 枚还是 10 枚。
- 只有 `threshold` 降到 0.7 才 2 倍过计数；只有 `dedup` 加到 40 才并计数。
- 3 枚间距 17px（重叠遮挡）→ 只数出 1：这是**图像遮挡**导致模板只匹配到一枚完整硬币，
  不是 dedup 逻辑的错，因此**不能**当作对抗性触发器。

---

## 4. 一个我自己造出来又撤回的假阳性（记录在案）

第一次跑嵌套 `ssh 'docker run ... bash -c "..."'` 时，`select='eq(pict_type,I)'` 报
`No such filter: 'I)'`，看起来像「SKILL.md 的 Method 1 命令本身是坏的」。
写成脚本文件重跑后：**`-vf "select='eq(pict_type,I)'"` exit=0、抽出 8 帧，命令是好的**。
之前那次是我的多层引号被 shell 吃掉导致的。**该结论已撤回。**

---

## 5. 对整体实验的含义

1. **「审计报告里的 finding」和「会被触发的 inconsistency」是两件事。** mario 的 5 条 finding
   静态看都成立，动态一条都不成立 —— 因为它们全都是**条件式**的（"若环境是 IM7/ffmpeg7/缺 cv2"），
   而条件在本环境为假。
2. **判定触发与否不需要跑 agent。** 每条 finding 的触发条件都可以在真实镜像里用一条确定性命令
   证伪 —— 这次 5 条只花了几分钟、0 次模型调用。**应该先用这个廉价筛子过一遍全部 finding，
   只把「条件成立但不确定影响」的少数留给 agent 实验。**
3. **mario 不是合适的对抗性实验对象**，因为它的 skill 在出厂数据上是正确的；
   要让它的 finding 触发，需要改**环境**（换 ffmpeg 7 / IM7 / 卸掉 cv2），那是环境扰动实验，
   不是任务数据扰动实验。

---

## 6. 下一步

把同一套**机械一致性探针**推广到服务器上已有的另外 9 个冻结任务
（civ6-adjacency-optimizer、grid-dispatch-operator、data-to-d3、dialogue-parser、
crystallographic、energy-market-pricing、court-form-filling、fix-druid、fix-erlang），
对每条 finding 判定触发条件是否成立；只对「条件成立」的条目做对抗性数据设计 + 配对 agent 实验。

**候选优先级**（按触发条件的可构造性）：

| 任务 | 候选 finding | 触发条件 | 对抗性数据设计 |
|---|---|---|---|
| `grid-dispatch-operator` | F-002（silent）成本函数系数在两个文档里不一致 | 条件天然成立（两份文档并存） | 构造使两套系数给出不同调度的负荷数据 |
| `data-to-d3` | F-002（verified+blocking）、F-003/F-004（silent）bubble 语义 | 条件待验证 | 构造两种语义给出不同答案的数据 |
| `civ6-adjacency-optimizer` | 邻接规则表缺项（旧审计发现，新审计漏报） | 需构造含该区域的场景 | 场景使缺失规则决定总分 |
| `crystallographic` | F-001/F-003（silent）| 条件待验证 | 构造落在分歧区间的结构数据 |

---

## 附录：原始证据

- 一致性探针脚本：`/tmp/adv_probe/conformance_test.sh`（服务器 `10.0.0.64`）
- dedup 参数敏感性探针：`/tmp/adv_probe/probe_dedup.py`
- 任务复现脚本：`/tmp/adv_probe/replicate.sh`
- 运行方式（无模型、无网络）：
  ```
  ssh user@10.0.0.64 \
    'docker run --rm -v /tmp/adv_probe:/w anonymous/mario-coin-counting:9d7ba40d718d bash /w/conformance_test.sh'
  ```
