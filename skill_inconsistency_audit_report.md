# Skill 不一致性综合审计报告

- **审计日期**：2026-09-17
- **数据来源**：`tool_audit_result/` 目录（10个任务，20份报告）
- **审计模型**：claude-sonnet-4-6
- **覆盖任务**：10 个

---

## 一、全局概览

| 任务 | 总 Finding | 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low | 阻断执行 | 静默错误 |
|---|---|---|---|---|---|---|---|
| civ6-adjacency-optimizer | 13 | 1 | 4 | 6 | 2 | 3 | 10 |
| court-form-filling | 16 | 0 | 7 | 7 | 2 | 6 | 9 |
| crystallographic-wyckoff | 25 | 1 | 3 | 18 | 3 | 1 | 11 |
| data-to-d3 | 15 | 0 | 5 | 9 | 1 | 0 | 14 |
| dialogue-parser | 13 | 2 | 5 | 3 | 3 | 0 | 11 |
| energy-market-pricing | 17 | 0 | 5 | 10 | 2 | 2 | 15 |
| fix-druid-loophole-cve | 18 | 0 | 8 | 7 | 3 | 6 | 10 |
| fix-erlang-ssh-cve | 13 | 0 | 4 | 9 | 0 | 0 | 7 |
| grid-dispatch-operator | 6 | 0 | 1 | 5 | 0 | 0 | 5 |
| mario-coin-counting | 10 | 0 | 6 | 3 | 1 | 3 | 7 |
| **合计** | **146** | **4** | **48** | **77** | **17** | **21** | **99** |

**关键比例**：
- 阻断执行（会直接导致 Agent 崩溃）：21 处，占 **14.4%**
- 静默错误（Agent 运行但产生错误结果）：99 处，占 **67.8%**
- Critical + High 合计：52 处，占 **35.6%**

---

## 二、不一致性类型分布

| 缺陷类型 | 数量 | 典型任务 |
|---|---|---|
| `interface_contract_mismatch`（接口契约不匹配） | ~28 | dialogue-parser, grid-dispatch-operator, energy-market-pricing |
| `environment_fact_conflict`（环境事实冲突） | ~25 | civ6-adjacency-optimizer, mario-coin-counting, data-to-d3 |
| `external_resource_invalid`（外部资源失效） | ~18 | court-form-filling, fix-druid-loophole-cve, civ6-adjacency-optimizer |
| `unimplemented_feature`（过度承诺/未实现功能） | ~22 | fix-erlang-ssh-cve, court-form-filling, crystallographic-wyckoff |
| `dependency_version_drift`（依赖版本漂移） | ~12 | mario-coin-counting, energy-market-pricing, grid-dispatch-operator |
| `cross_document_process_conflict`（跨文档流程冲突） | ~8 | energy-market-pricing |
| `side_effect_conflict`（副作用声明冲突） | ~6 | fix-druid-loophole-cve, court-form-filling, fix-erlang-ssh-cve |
| `missing_constraint_or_exception`（缺失约束说明） | ~7 | data-to-d3, dialogue-parser |
| **合计** | **~126** | — |

---

## 三、逐任务影响分析

### 3.1 civ6-adjacency-optimizer
**严重程度：高**（含 1 Critical）

**核心不一致及任务影响**：

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-003 | 🔴 Critical | `placement_rules.py` 裸导入 `hex_utils`，SKILL.md 声明路径为 `src.hex_utils` | 所有放置验证功能在标准 Python 路径下将抛出 `ModuleNotFoundError`，**区域放置任务完全无法执行** |
| F-001/002 | 🟠 High | Fandom Wiki URL 失效（adjacency_bonus、District） | 若 Agent 尝试访问文档注释中的 URL 作为运行时引用，**直接阻断**；作为代码注释则不影响运行但影响调试 |
| F-004 | 🟠 High | `calculate_district_adjacency` 签名文档示例与实现不符 | Agent 按文档示例调用将得到错误结果，**邻接分数计算静默出错** |
| F-008 | 🟡 Medium | `COMMERCIAL_HUB_RULES` 的河流+2规则在常量表中缺失，仅通过特判实现 | Agent 生成的规则摘要将遗漏该加成，**商业中枢优化结果偏低** |
| F-013 | 🟢 Low | BATH 区划在文档中提及但 `DistrictType` 枚举中缺失 | 涉及 Bath 的邻接规则匹配静默失败，**工业区优化分数可能偏低** |

**总结**：Critical 级别的模块路径冲突会直接阻断核心功能；即使绕过，邻接计算逻辑和规则表的文档/代码不一致仍会导致优化结果不可信。

---

### 3.2 court-form-filling
**严重程度：高**（含 7 High）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-001 | 🟠 High | 文档声明无副作用但脚本实际写入文件 | 沙箱/只读环境下**直接阻断**所有表单脚本执行 |
| F-002/003 | 🟠 High | Adobe PDF 规范 URL 和 pypdf GitHub issue URL 失效 | 依赖这些 URL 的运行时获取逻辑**阻断执行** |
| F-004 | 🟠 High | `pypdf` 依赖未在文档中声明 | 无该库的环境中导入阶段即**崩溃** |
| F-005/006 | 🟠 High | `dpi=200` 分辨率限制和最大 1000px 约束未在文档中说明 | Agent 在高精度场景下不知晓此限制，坐标计算精度受损，**表单填写位置可能偏移** |
| F-007 | 🟠 High | `pdf-lib`（JS）和 Python 脚本路径在文档中并列但无互斥说明 | Agent 可能混用两种技术栈，**在 Python 环境中生成无效的 JS 代码** |
| F-016 | 🟡 Medium | 批量处理在描述中承诺但未实现 | Agent 尝试批量填写时无入口，任务需逐文件手动调用 |

**总结**：副作用声明冲突和未声明依赖可以导致执行环境崩溃；分辨率限制的隐藏会在实际法院表单填写中产生坐标偏移，直接影响任务输出质量。

---

### 3.3 crystallographic-wyckoff
**严重程度：高**（含 1 Critical，25 个 Finding）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-001（Critical） | 🔴 Critical | `structure_analyzer.py` 用 `get_symmetrized_structure()` 提取 Wyckoff，而 `wyckoff-positions-from-cif.md` 明确禁止该方法，要求用 `get_symmetry_dataset()` | **Wyckoff 位置提取方法错误**，结果在非标准化结构上不可复现，核心任务目标可能产生错误输出 |
| F-014 | 🟠 High | `sympy` 代码示例中未导入 `sin`、`cos` 等符号直接使用 | Agent 复制示例代码运行时抛出 `NameError`，**符号计算无法执行** |
| F-015 | 🟠 High | `MPRester` API Key 在文档中标注为可选，但实际访问 Materials Project 必须提供 | 未配置 API Key 的环境中，所有材料数据获取操作**静默返回空结果或抛出认证错误** |
| F-021 | 🟡 Medium | 相稳定性阈值 `0.001 eV/atom` 在 SKILL.md 和脚本中定义不一致（脚本额外引入 METASTABLE 中间状态） | **相图稳定性判断标准不统一**，Agent 调用不同来源的代码会得到不同分类结果 |
| F-023 | 🟢 Low | 批量通配符转换依赖 `Path.cwd().glob()` 而非 shell 展开，部分环境下行为异常 | 批量转换命令在某些 shell 中**静默处理错误文件集合** |

**总结**：Critical 级别的 Wyckoff 提取方法矛盾直接影响任务核心输出；sympy 未导入符号可以导致计算任务阻断；Materials Project API 声明含糊会导致数据获取静默失败。

---

### 3.4 data-to-d3
**严重程度：中**（无 Critical，但 14 处静默错误）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-002 | 🟠 High | 力导向模拟未固定 tick 数，违反文档的确定性约束 | **每次运行布局不同**，无法复现，违背任务确定性要求 |
| F-005 | 🟠 High | 文档 description 标注 D3.js v6，正文和 vendor 文件使用 v7 | Agent 按 v6 API 写代码，实际 vendor 是 v7，`d3.event` 等 breaking change **导致可视化静默失败** |
| F-007 | 🟠 High | `highlightTableRow`/`highlightBubble` 函数在脚本间互调但接口未在 SKILL.md 中声明 | Agent 独立实现两个组件时**无法建立正确的联动关系** |
| F-008 | 🟠 High | 交互式表格输出格式（.html 含 `<table>`）未在输出规范中声明 | Agent 可能只生成 SVG/PNG，**遗漏交互表格组件** |
| F-015 | 🟡 Medium | CSV 数据排序（确定性要求）在示例代码中缺失 | 输出依赖 CSV 行序，**跨运行结果不一致** |
| F-004 | 🟢 Low | tooltip 使用 CSS transition，违反「禁止动画」约束 | 无头渲染/截图场景下存在**时序竞争风险** |

**总结**：D3 版本冲突和力模拟确定性问题是最高风险，会直接导致可视化结果在不同运行间不一致，破坏任务的可复现性要求。

---

### 3.5 dialogue-parser
**严重程度：高**（含 2 Critical）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-005 | 🔴 Critical | `Edge.to_dict()` 序列化为 `from`/`to`，但文档使用 `source`/`target` | Agent 按文档构造下游解析逻辑时**静默找不到边数据**，序列化往返失败 |
| F-006 | 🔴 Critical | `from_dict()` 内部读取 `e['from']`，但文档示例暗示使用 `source`/`target` | Agent 按文档构造输入字典时抛出 `KeyError`，**反序列化完全失败** |
| F-002 | 🟠 High | `validate()` 错误消息格式文档与实现不一致 | 任何对错误消息进行字符串匹配的上层逻辑**静默失败** |
| F-003 | 🟠 High | `visualize()` 硬编码 6 个 speaker 颜色，超出后复用颜色但文档未说明限制 | 超过 6 人对话时**视觉混淆，任务输出可读性下降** |
| F-004 | 🟠 High | `from_dict()` 直接操作 `graph.nodes` 而非调用 `add_node()`，绕过重复 ID 检查 | 含重复 ID 的输入数据**静默覆盖节点，不触发验证错误** |

**总结**：两个 Critical 级别的序列化键名不一致（source/target vs from/to）是该任务最严重的问题，会导致对话图的序列化/反序列化链路完全断裂，任何依赖持久化或跨组件传递图数据的场景都会失败。

---

### 3.6 energy-market-pricing
**严重程度：高**（17 个 Finding，含多处跨文档流程冲突）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-001 | 🟠 High | `cp.CLARABEL` 求解器依赖 CVXPY ≥1.3.0，文档未声明版本要求 | 旧版环境中**求解阶段崩溃**，整个定价优化任务无法完成 |
| F-008 | 🟠 High | `balance_constraints` 需由 economic-dispatch 构建并传递给 LMP 模块，但 economic-dispatch 文档未提及 | Agent 按各模块文档独立实现时**LMP 对偶值无法提取**，节点电价全为 None |
| F-009 | 🟠 High | `reserve_con` 同样存在跨文档责任归属矛盾 | 备用出清价格**静默为 None 或缺失** |
| F-012 | 🟡 Medium | `calculate_line_flows()` 返回 `limit_MW`，SKILL.md 文档使用 `rating_MW` | 下游访问 `rating_MW` 字段时得到 `KeyError` 或 `None`，**线路载流率计算静默失败** |
| F-017 | 🟡 Medium | `generator_dispatch` 输出的 `bus` 字段未说明是原始总线号还是 0-indexed 索引 | 下游将其作为数组索引时**越界或访问错误节点** |

**总结**：energy-market-pricing 的问题集中在跨技能接口链路上。`balance_constraints` 和 `reserve_con` 的归属冲突意味着完整 DC-OPF 定价流水线无法仅靠文档自洽地组装，Agent 必须"猜测"哪个模块负责哪段逻辑。

---

### 3.7 fix-druid-loophole-cve
**严重程度：高**（18 个 Finding，6 处阻断执行）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-001 | 🟠 High | 文档声明只读无副作用，但 `api_endpoint_generator.py` 实际写入文件 | 只读/沙箱环境下**所有代码生成操作阻断** |
| F-004/005/006 | 🟠 High | Maven POM URL（404）和 localhost URL（502）失效 | 依赖这些 URL 的 XML namespace 声明和 CORS 配置**在运行时抛出连接错误** |
| F-007 | 🟠 High | `spring_project_scaffolder.py` 和 `security_config_generator.py` 都生成 `SecurityConfig.java` 到同一路径 | 两脚本顺序执行时**后者覆盖前者**，生成的安全配置不完整（scaffolder 版本缺少 JWT EntryPoint） |
| F-010 | 🟡 Medium | `performance_profiler.py` 文档声称支持在线 profiling（`--profile http://...`）但实现仅支持静态扫描 | Agent 尝试在线 profiling 时**得到 `AttributeError` 或空结果**，无法完成动态分析 |
| F-018 | 🟢 Low | `--check-security` 标志语义反转（文档暗示为启用，代码默认为 True） | Agent 认为不传该标志即不做安全扫描，实际上**安全扫描始终执行** |

**总结**：CVE 修复任务中最危险的问题是 SecurityConfig.java 的文件冲突——两个脚本写同一文件会导致安全配置被截断版覆盖，直接削弱修复效果。未实现的在线 profiling 功能也让 Agent 无法完成动态验证。

---

### 3.8 fix-erlang-ssh-cve
**严重程度：中**（13 个 Finding，无阻断执行）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-007 | 🟠 High | `senior-security` 三个脚本均为空实现（`analyze()` 返回空列表） | Agent 调用安全审计/威胁建模脚本**得到零 findings，误认为代码安全** |
| F-009 | 🟠 High | `erlang-otp-behaviors` 声明涵盖 `gen_event` 但无任何示例 | 需要 `gen_event` 指导时 Agent **无法获取实质性帮助** |
| F-011 | 🟠 High | `ssh-penetration-testing` 与 `senior-security/penetration-testing` 功能重叠，触发条件无明确区分 | Agent 在渗透测试场景下**选择错误的技能**（senior-security 是空壳），任务无实质输出 |
| F-013 | 🟡 Medium | `worker_loop()` 只匹配两种消息，违反文档「处理所有消息」的最佳实践 | 其他消息静默积累，**进程可能内存泄漏或调用方永久挂起** |

**总结**：`senior-security` 技能是名副其实的"空壳"——文档声称完整的安全工程能力，实际三个脚本都是占位模板，对于 CVE 修复任务中的安全验证环节完全无效。Agent 会产生"已完成安全审计"的错误置信。

---

### 3.9 grid-dispatch-operator
**严重程度：低**（6 个 Finding，无阻断执行，问题集中于接口字段命名）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-004 | 🟠 High | `calculate_line_flows()` 返回 `limit_MW`，文档使用 `rating_MW` | 下游访问时 `KeyError`，**线路载流率计算失败** |
| F-002 | 🟡 Medium | 文档公式 `loading_pct = abs(flow_MW) / rating_MW * 100` 未处理 `RATE_A=0` 边界 | 直接使用文档代码时**除零错误**（MATPOWER 中 RATE_A=0 是合法值） |
| F-003 | 🟡 Medium | `dc-power-flow` 中 `rating_MW` 来自 `branch[5]`，`power-flow-data` 同列标注为 `rating (MVA)`，单位和命名语义模糊 | 跨模块拼接代码时**单位混淆，功率计算结果偏差** |
| F-005 | 🟡 Medium | `bus_num_to_idx` 映射责任分散在多个技能中 | Agent 可能**重复实现或遗漏映射**，导致总线索引不一致 |

**总结**：grid-dispatch-operator 问题相对集中，核心痛点是 `limit_MW` vs `rating_MW` 的字段命名冲突，这个单点问题会在整个电力调度流水线的下游引发连锁的 KeyError。

---

### 3.10 mario-coin-counting
**严重程度：高**（10 个 Finding，3 处阻断执行）

| # | 严重度 | 不一致描述 | 对任务的影响 |
|---|---|---|---|
| F-001 | 🟠 High | FFmpeg 使用 `-vsync vfr`，FFmpeg 5.x+ 已弃用，应改为 `-fps_mode vfr` | 新版 FFmpeg 环境中**关键帧提取命令执行失败**，无法获得输入帧 |
| F-002 | 🟠 High | ImageMagick 文档假设 `convert` 命令可用，但 ImageMagick 7 已改为 `magick` | 新版环境中**所有图像处理操作阻断** |
| F-004 | 🟠 High | `count_objects.py` 依赖 `cv2`/`numpy` 但 SKILL.md 未声明这些依赖 | 未预装环境中**导入阶段即崩溃** |
| F-005 | 🟠 High | ffmpeg 输出彩色图像，但 object-counter 内部强制以灰度读取，文档未说明 | 彩色图像传入后**静默转灰度**，模板匹配精度受损，计数结果可能偏低 |
| F-006 | 🟠 High | `denoise`/`super_resolution` 工具选项存在代码中但实现抛出 `NotImplementedError`，文档完全未提 | Agent 尝试调用降噪功能时**立即崩溃** |

**总结**：该任务面临典型的"工具版本断层"问题——FFmpeg 和 ImageMagick 的版本变更已使文档中的命令在现代系统上失效；加之未声明的 cv2/numpy 依赖，任务在全新环境中几乎无法开箱即用。

---

## 四、跨任务共性缺陷分析

### 4.1 环境版本断层（影响 6/10 任务）

> **模式**：Skill 文档假设特定版本的工具/库，但现实部署环境已升级

| 任务 | 受影响组件 | 具体冲突 |
|---|---|---|
| mario-coin-counting | FFmpeg 5.x | `-vsync` → `-fps_mode` |
| mario-coin-counting | ImageMagick 7 | `convert` → `magick` |
| energy-market-pricing | CVXPY 1.3.0 | `cp.CLARABEL` 不存在于旧版 |
| grid-dispatch-operator | CVXPY 1.3.0 | 同上 |
| court-form-filling | pypdf | 依赖版本未声明 |
| data-to-d3 | D3.js v6 vs v7 | description 与 vendor 版本不一致 |

**影响**：Agent 在全新环境中执行时，这类错误在依赖安装阶段就会暴露，但因为文档未声明版本要求，Agent 无法给出正确的安装指令。

### 4.2 序列化接口键名冲突（影响 3/10 任务）

> **模式**：输出字段的命名在文档与实现之间不一致，且往往是低调的细节差异（`source` vs `from`，`rating_MW` vs `limit_MW`）

| 任务 | 冲突字段 | 影响 |
|---|---|---|
| dialogue-parser | `source`/`target` vs `from`/`to` | 序列化往返完全断裂（2 个 Critical） |
| grid-dispatch-operator | `rating_MW` vs `limit_MW` | 下游 KeyError |
| energy-market-pricing | `rating_MW` vs `limit_MW` | 同上 |

**影响**：这类问题特别危险，因为 Agent 会通过文档学到"正确"的字段名，再去访问实现中"错误"的字段名，导致 KeyError 或静默返回 None，且不会有任何警告。

### 4.3 过度承诺/空实现（影响 4/10 任务）

> **模式**：文档声称功能完整，但实现要么缺失要么是占位符

| 任务 | 虚假功能 | 实际状态 |
|---|---|---|
| fix-erlang-ssh-cve | senior-security 三大安全工具 | `analyze()` 返回空列表 |
| mario-coin-counting | `denoise`/`super_resolution` | `NotImplementedError` |
| court-form-filling | 批量 PDF 处理 | 无批量入口 |
| fix-druid-loophole-cve | 在线 performance profiling | 仅支持静态扫描 |

**影响**：最危险的是 `senior-security` 的空实现——Agent 会产生"安全审计已完成"的错误置信，在 CVE 修复场景中这是一个严重的安全盲点。

### 4.4 跨 Skill 流程责任不明（影响 2/10 任务）

> **模式**：多技能协作时，关键的中间状态（对象引用、数据结构）的构建责任在文档中未指定，导致 Agent 组装流水线时遗漏关键步骤

| 任务 | 冲突点 |
|---|---|
| energy-market-pricing | `balance_constraints` 和 `reserve_con` 的存储责任：economic-dispatch 文档不提，LMP 文档重新定义 |
| civ6-adjacency-optimizer | `hex_utils.py` 在 `civ6lib` 和 `hex-grid-spatial` 中完全重复，维护双轨 |

---

## 五、风险优先级矩阵

按**任务成功率影响 × 修复成本**排序：

| 优先级 | 问题 | 涉及任务 | 推荐修复 |
|---|---|---|---|
| P0 | dialogue-parser 序列化键名 (`from`/`to` vs `source`/`target`) | dialogue-parser | 统一 Edge 序列化键为 `source`/`target`，与类属性对齐 |
| P0 | civ6 模块路径冲突 (`hex_utils` vs `src.hex_utils`) | civ6-adjacency-optimizer | 统一导入路径，或在 SKILL.md 中说明运行时路径配置 |
| P0 | senior-security 空实现 | fix-erlang-ssh-cve | 在文档中明确标注为"占位符/待实现"，避免 Agent 误信 |
| P1 | energy-market-pricing `balance_constraints` 归属冲突 | energy-market-pricing | 在 economic-dispatch 文档中明确添加"存储 balance_constraints 供 LMP 使用"步骤 |
| P1 | crystallographic-wyckoff Wyckoff 提取方法矛盾 | crystallographic-wyckoff | 删除 `structure_analyzer.py` 中的 `get_symmetrized_structure()` 用法，统一使用 `get_symmetry_dataset()` |
| P1 | mario-coin-counting FFmpeg/ImageMagick 版本断层 | mario-coin-counting | 更新所有示例命令，添加版本检测逻辑，或在前置条件中说明版本要求 |
| P1 | `limit_MW` vs `rating_MW` 字段命名 | grid-dispatch-operator, energy-market-pricing | 统一为 `rating_MW`（与文档对齐），更新实现代码 |
| P2 | D3.js v6/v7 版本描述矛盾 | data-to-d3 | 修正 SKILL.md description 字段，统一声明 `d3@7.9.0` |
| P2 | court-form-filling 未声明 pypdf 依赖 | court-form-filling | 在 SKILL.md Prerequisites 中添加 `pypdf>=3.0` 依赖声明 |
| P2 | CVXPY `cp.CLARABEL` 版本要求 | energy-market-pricing, grid-dispatch-operator | 在依赖声明中添加 `cvxpy>=1.3.0` |
| P3 | 失效外部 URL（Fandom Wiki、Adobe PDF 规范等） | 多任务 | 将 URL 改为纯注释引用，移除运行时依赖 |
| P3 | data-to-d3 力模拟确定性 | data-to-d3 | 添加 `simulation.stop()` 和固定 tick 数调用 |

---

## 六、总结

**146 个 Finding** 分布在 10 个任务中，其中 4 个 Critical、48 个 High 级别缺陷代表了 Agent 执行失败的主要风险来源。

三类问题尤为突出：

1. **接口契约不匹配**是最隐蔽的问题类型。Agent 通过文档学到一套字段名/方法签名，代码实际使用另一套，产生的 KeyError 或 None 值往往不带明显错误信息，导致任务在"看似成功"的情况下悄然产出错误结果。

2. **过度承诺的空实现**在安全类任务中危害最大。`senior-security` 的三个空脚本会让 Agent 对安全状态产生错误的置信，这在 CVE 修复场景下是直接风险。

3. **工具版本断层**随着底层工具（FFmpeg、ImageMagick、CVXPY）的版本演进不断累积，现有文档假设的工具版本已在多数现代环境中过时，是最容易在全新部署中触发的阻断问题。

---

*报告生成时间：2026-09-17*
