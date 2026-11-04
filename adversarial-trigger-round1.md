# 对抗性触发实验 · 第 1 轮：目标筛查与两个试点

**目标**：构造语义等价的输入扰动，使已审计的不一致性**必然被触发**，再在真实服务器上做配对实验。

**本轮结论（先说）**：对抗性**任务数据**能触发的不一致性，比预期少得多。
我逐个任务实测了服务器上 10 个冻结任务中最有希望的 4 个，只有 **1 个**的 finding 是真正
「由数据决定触发」的；另外 3 个的 finding 分别属于「条件式环境假设」「agent 行为依赖」
「agent 绕过 skill 即可规避」，**改任务数据无法把它们逼出来**。

---

## 1. 方法：机械一致性探针（本轮最有价值的产出）

关键认识：**判定一条 finding 有没有被触发，不需要跑 agent。**

每条 finding 的触发条件都能在真实任务镜像里用一条确定性命令证伪：

```
ssh user@10.0.0.64 \
  'docker run --rm -v /tmp/adv_probe:/w <image> bash /w/<probe>.sh'
```

- 0 次模型调用、0 次 reward 依赖、可无限复现；
- 覆盖环境事实（版本、二进制、已装包）、文档命令可执行性、脚本行为；
- 只有「条件成立但影响幅度未知」的少数条目，才值得花昂贵的配对 agent 实验。

---

## 2. 试点 A：`mario-coin-counting` —— 5 条 finding，**0 条被触发**

镜像 `anonymous/mario-coin-counting:9d7ba40d718d`。

| finding | 触发条件 | 实测 | 判定 |
|---|---|---|---|
| F-001 `convert` 在 IM7 不存在 | 环境为 ImageMagick 7 | ImageMagick **6.9.12**，`convert` 可用 | 未触发 |
| F-002 SKILL.md 未声明 cv2/numpy | 环境缺 cv2 | 已装 **cv2 4.12.0 / numpy 2.2.6** | 未触发 |
| F-003 `-vsync` 在 ffmpeg 7 被移除 | ffmpeg ≥ 7 | **ffmpeg 6.1.1**，`-vsync vfr` exit=0 | 未触发 |
| F-004 cosmetic | — | — | 跳过 |
| F-005 `--dedup_min_dist` 文档说可选、实为 required | agent **省略**该 flag | 文档示例**带了** flag | 条件存在但未被触发 |

**skill 功能正确性**：按 SKILL.md 推荐参数（`--threshold 0.9 --dedup_min_dist 3`）完整复现任务，
与出厂 `expected_output.csv` 对比 **8/8 帧完全一致**。也就是说，照文档做就一定满分。

**合成图像参数敏感性**（真值已知）：推荐参数在物体不重叠时 1/2/5/10 枚全部正确；
threshold→0.7 才 2 倍过计数，dedup→40 才并计数；重叠遮挡只数出 1 枚是**图像遮挡**而非 dedup 逻辑问题。

**结论**：mario 不是合适的对抗性实验对象。要触发它需要改**环境**（换 ffmpeg7/IM7/卸 cv2），
那是环境扰动实验，不是任务数据扰动实验。

> 附：本轮我自己造过一个假阳性 —— 嵌套 `ssh 'docker run … bash -c "…"'` 时
> `select='eq(pict_type,I)'` 报 `No such filter: 'I)'`，看起来像 SKILL.md 命令是坏的。
> 写成脚本文件重跑后 exit=0、抽出 8 帧，**命令是好的**，是我的多层引号被 shell 吃掉。已撤回。

---

## 3. 试点 B：`grid-dispatch-operator` —— 机制成立，但任务在地板上

**Finding F-002（medium / inferred / `silent`）**：技能的
`economic-dispatch/references/cost-functions.md` 明确把 MATPOWER **Type 1 分段线性成本**
列为受支持格式并给出示例 `gencost = [1,0,0,3,0,0,50,1000,100,2500]`；
而技能的 `SKILL.md` 目标函数**只按 NCOST 分支**，从不读 `gencost[i,0]`（MODEL 列）。

**我在任务 verifier 里发现了同一处缺陷**：`verifier/test_outputs.py` 的 `optimal_cost` fixture
同样直接 `c2, c1, c0 = gencost[i,4], gencost[i,5], gencost[i,6]`，完全忽略 MODEL。
即**技能与评分器以同样错误的方式读数据**。

**出厂数据**：510 台机组的 gencost **全部是 MODEL=2、NCOST=3**，所以这条 bug 处于休眠状态。

**对抗性设计（语义等价）**：把若干台纯线性成本机组的成本**重新编码**为 3 点**共线**的 Type-1 行
（`y = c1·x + c0`）。真实经济性完全不变 —— 变的只是评分器会把断点当成 c2/c1/c0。

**预检查（进行中）**：三种解的对比
1. 评分器在出厂数据上的 optimal；
2. 评分器在对抗数据上的 optimal（把断点当多项式系数）；
3. 经济上正确的 optimal（把断点当分段线性）。

预期：第 2 与第 3 相差远超 verifier 的 ±0.01% 容差，
于是**忠实实现参考文档的 agent 会被判超下限 gap 而失败**。

**但它不是好的 agent 级实验对象**：本仓此前 60/1M 与 400/8M 两次实验里
`grid-dispatch-operator` 三个 arm 全部 0/3 —— 任务在成功率地板上，
任何 skill 造成的失败都观察不到。**机制可用作单元级证据，不能用作 effectiveness 证据。**

---

## 4. 另外两个候选：finding 是「agent 行为依赖」，不是「数据依赖」

我先按「基线成功率高、有区分度」筛出本 harness 内真正有 headroom 的三个任务
（crystallographic 0.88、dialogue-parser 0.83、mario 0.67），逐一核对其 finding 的可触发性。

### 4.1 `dialogue-parser`（6 条 finding，全部依赖 agent 的写法）

| finding | 类型 | 为什么数据逼不出来 |
|---|---|---|
| F-001/F-005/F-006 | `validate()` 返回消息格式与文档不符 | 只有 agent 去**正则匹配文档措辞**才会静默漏错；不解析就无影响 |
| F-003 | 文档写 `Node(id, speaker, text, type)`，实现是 `(id, text, speaker, type)` | 文档示例用**关键字传参**；只有 agent 改用**位置传参**才踩 |
| F-004 | `End` 哨兵语义未声明 | 概念冲突，与输入数据无关 |
| F-002 | 缺 Graphviz 二进制时抛未捕获异常 | 环境里二进制存在 → 条件不成立 |

输入 `script.txt` 我完全可以自造，但这些 finding 的正确与否**不由数据决定**。

### 4.2 `crystallographic-wyckoff`（3 条 finding，都是技能自带脚本的文档夸大）

- F-001（`silent`）：脚本把一列表头写成 "Wyckoff"，实际填的是
  `equivalent_sites[0][0].species_string`（**元素名，不是 Wyckoff 字母**）。
  agent 只要不用这个脚本、直接用 pymatgen 的 `wyckoff_symbols` 就不会踩。
- F-002/F-003：文档声明了 `--distances` 的适用约束、键角计算等**未实现能力**。

verifier 的 `EXPECTED_RESULTS` 硬编码 10 个 CIF 的期望值（Wyckoff 字母 → 多重度/坐标），
CIF 是可改的数据；但改 CIF 只能改变**真值**，不能改变「agent 是否采用技能那条捷径」。
基线 0.88 说明 agent 大多数时候绕开了它。

---

## 5. 本轮形成的判断

**这台 benchmark 上，audited inconsistency 的可触发性分三类：**

| 类别 | 触发由什么决定 | 对抗性任务数据能否逼出 | 例子 |
|---|---|---|---|
| **A. 条件式环境假设** | 环境版本/已装包/二进制 | ✗ 要改**环境**（换镜像） | mario F-001/F-002/F-003；dialogue F-002 |
| **B. agent 行为依赖** | agent 是否照抄文档的调用约定 | ✗ 与数据无关 | dialogue F-003/F-001；crystallographic F-001 |
| **C. 数据格式依赖** | 输入数据用哪种格式 | ✓ **可以** | grid F-002（Type-1 gencost） |

**只有 C 类适合「对抗性任务数据」这条路线。** 目前 10 个冻结任务里，
我找到的 C 类条目只有 `grid-dispatch-operator` F-002 一条，
而它所在任务处于成功率地板，reward 层面观察不到差异。

这解释了为什么此前三组对照实验里 skill repair 对 effectiveness 几乎没有影响：
**被审计出来的不一致性，绝大多数在给定数据与给定环境下的触发条件为假。**

它与另一个已有结论互为印证：`skill-audit` 对 5 条由轨迹证实的真实不一致性命中 0 条
（见 `skill-audit/OPTIMIZATION.md` §5 待补的 `task_contract_checker`）——
**检测器抓到的多为「静态成立但动态不触发」的文档级问题，
而真正影响运行的问题（如 mario 的关键帧方法选择、sec-financial 的目录布局）
没有被抓成 finding。**

---

## 6. 下一步（第 2 轮）

**先修正一个前提**：我此前只在服务器上已有的 10 个冻结任务里找目标，因此被
「有 headroom 的任务只有 3 个、而这 3 个的 finding 都不可数据触发」卡住。
但服务器是**可以构建新镜像的**（`build-images.sh` 从 `inputs/selected_tasks/<task>/environment` 构建，
Docker + 网络都可用）。把范围放宽到全部 87 个任务后，最好的目标是：

### 6.1 首选：`earthquake-plate-calculation`（新建镜像）

| 项 | 值 |
|---|---|
| 基线成功率 | **67%**（paper-v1 with-skills，3 次运行），有充足 headroom |
| 成本 | 中位总耗时 98 s、31.8 万 token —— 便宜，适合多 trial |
| 规模 | 3 个 JSON 数据文件、9 条 finding、9 条达到文件级暴露 |
| 数据可控性 | `earthquakes_2024.json` / `PB2002_plates.json` / `PB2002_boundaries.json` **全部由我编造**，真值由 verifier 从数据算出 |

**数据依赖的触发设计（C 类）**：finding F-005 指出技能的 `geospatial-analysis` 文档
**同时**给出两套互斥的字段名 ——
`gdf_plates["Name"]` vs `gdf_plates["PlateName"]`，以及 `lon/lat` vs `longitude/latitude`。
数据用哪一套，就决定照抄哪一段示例的 agent 会 `KeyError`。
把数据字段名定在文档**第二套**示例上，使照抄**第一套**（更显眼的那段）的 agent 必然失败。
这是语义等价的（数值不变，只改键名），且 verifier 从数据反算真值，无需改 ground truth。

**配对设计**：original skill vs 最小修复 skill（把文档里那套用不到的字段名删掉/统一），
各 3 trial，同一份对抗数据；另加一组出厂数据的基线对照。

### 6.2 备选：`lab-unit-harmonization`（新建镜像）

基线 51%，数据是我全权编写的 CSV。finding F-001 是「文档声称能清洗千位分隔符、实现不能」。
注意：task.md 明说 `,` 是小数点，所以塞入 `1,234.5` 会与 task 说明冲突 ——
**这条要判定为「对抗数据不合法」还是「文档过度承诺」，需要单独论证**，因此排在第二位。

### 6.3 收尾动作

1. **收口 grid 预检查**（容器仍在跑：cvxpy 1.4.2 从源码构建中），拿到三种解的具体数值，
   作为 C 类机制的单元级证据 —— 但它所在任务在成功率地板上，只作机制证据不作效果证据。
2. **把机械一致性探针推广到全部 10 个冻结任务**，产出一张完整的
   「finding × 触发条件 × 实测成立与否」表。
3. 环境扰动路线（A 类，如用 ffmpeg 7 重建 mario 镜像）暂缓，等数据扰动路线的结果出来再决定。

---

## 7. 附带完成：29 份失效报告已全部重跑，排序已按完整数据重算

上一轮定位的 comprehension 静默失效（`_extract_json` 解析失败时返回空骨架并被缓存）已修复并重跑：

| 项 | 修复前 | 修复后 |
|---|---|---|
| 可用报告 | 58 / 87 | **87 / 87** |
| finding 总数 | 260 | **377**（+45%） |
| 其中 `silent` 类 | 116 | **179** |
| Top 30 可参与排序的任务 | 31 | **47** |

重算后的 Top 30 明显换血（此前因报告无效而缺席的任务进入榜单）：
`travel-planning` #4、`data-to-d3` #7、`weighted-gdp-calc` #8、`reserves-at-risk-calc` #10、
`paper-anonymizer` #12、`shock-analysis-supply` #14、`shock-analysis-demand` #22、
`multilingual-video-dubbing` #23、`grid-dispatch-operator` #28。

轨迹因果表同步更新：`court-form-filling` 现在是 **STRONG 级 effectiveness+efficiency 双降**
（14 次报错、34% 轮次用于恢复、skill 自身代码在 2/3 运行中崩溃），但排在 Top 30 之外（#31）。

产物：`skill_inconsistency_impact_top30.md`、`skill_inconsistency_impact_ranking.csv`、
`skill_trace_causal_audit.md/.csv`。修复细节见 `skill-audit/comprehension/comprehension_agent.py`
与新增 5 条回归检查的 `skill-audit/tests/test_regressions.py`，重跑脚本 `analysis_tools/rerun_failed_audits.sh`。

---

## 附录：原始证据

| 文件 | 内容 |
|---|---|
| `/tmp/adv_probe/conformance_test.sh` | mario 一致性探针（服务器） |
| `/tmp/adv_probe/probe_dedup.py` | dedup 参数敏感性扫描 |
| `/tmp/adv_probe/replicate.sh` | mario 任务复现（计数结果 vs ground truth） |
| `/tmp/adv_probe/grid_precheck.py` | grid Type-1 对抗数据的三解对比 |
