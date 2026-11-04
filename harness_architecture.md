# Skill 不一致审计工具 —— Harness 架构设计

---

## 1. 完整目录树

```
skill-audit/
├── config.yaml                              # 全局配置文件
├── main.py                                  # CLI 入口
│
├── core/                                    # 核心流水线
│   ├── __init__.py
│   ├── pipeline.py                          # 主流水线编排器
│   └── aggregator.py                        # 缺陷聚合 & 去重
│
├── comprehension/                           # Skill 理解阶段（流水线最前置）
│   ├── __init__.py
│   ├── scanner.py                           # 目录扫描器，收集文件元信息
│   ├── comprehension_agent.py               # 两轮交互 LLM Agent，产出 SkillMap
│   └── skill_map.py                         # SkillMap 数据结构定义
│
├── hard_checkers/                           # 前置硬规则子工具（非LLM）
│   ├── __init__.py
│   ├── schema_comparator.py                 # 结构化 Schema 比对器
│   ├── code_parser.py                       # 代码语法静态解析器
│   ├── dependency_extractor.py              # 依赖图提取器
│   ├── url_validator.py                     # 外部资源有效性检查器
│   └── env_constraint_checker.py            # 环境声明冲突检查器
│
├── llm_checkers/                            # 多专项 LLM Checker
│   ├── __init__.py
│   ├── base_checker.py                      # 抽象基类
│   ├── env_layer_checker.py                 # 环境层不一致审计
│   ├── doc_layer_checker.py                 # 文档层不一致审计
│   ├── impl_over_promised_checker.py        # 实现层-过度承诺型
│   ├── impl_semantic_conflict_checker.py    # 实现层-语义冲突型
│   └── impl_under_promised_checker.py       # 实现层-承诺不足型
│
├── validator/
│   ├── __init__.py
│   └── criticality_validator.py             # 二次校验，过滤假阳性
│
├── llm_client/                              # LLM 后端适配层
│   ├── __init__.py
│   ├── base_client.py
│   ├── anthropic_client.py
│   ├── openai_client.py
│   └── openai_compatible_client.py
│
├── models/
│   ├── __init__.py
│   ├── skill_map.py                         # SkillMap、FileRole、ComponentRelation
│   ├── preflight.py                         # PreflightData（硬规则阶段产出汇总）
│   └── finding.py                           # Finding 数据类
│
├── report/
│   ├── __init__.py
│   └── reporter.py                          # JSON 报告序列化
│
├── prompts/
│   ├── comprehension_round1.md              # Round1：让LLM决定读哪些文件
│   ├── comprehension_round2.md              # Round2：产出 SkillMap
│   ├── env_layer.md
│   ├── doc_layer.md
│   ├── impl_over_promised.md
│   ├── impl_semantic_conflict.md
│   ├── impl_under_promised.md
│   └── criticality_validation.md
│
└── tests/
    ├── fixtures/
    │   └── sample_skills/                   # 各种非标准结构的测试 Skill 样本
    └── test_*.py
```

---

## 2. 各模块职责说明

### `main.py` — CLI 入口
- 解析命令行参数：`--skill-dir`、`--config`、`--output`、`--parallel`
- 初始化配置，构建 LLM Client，调用 `pipeline.py`
- 将最终报告写入指定路径

---

### `comprehension/scanner.py` — 目录扫描器

**职责**：递归扫描 Skill 目录，收集每个文件的轻量元信息，不读取文件内容。

**输出**：`List[FileEntry]`，每条包含：

| 字段 | 说明 |
|---|---|
| `path` | 相对 Skill 根目录的路径 |
| `extension` | 文件扩展名 |
| `size_bytes` | 文件大小 |
| `first_lines` | 文件前 3 行原文（用于辅助 Round1 决策） |

排除规则：忽略 `.git/`、`__pycache__/`、`*.pyc`、`.DS_Store` 等无关文件。

---

### `comprehension/comprehension_agent.py` — Skill 理解 Agent

流水线最前置模块，通过两轮 LLM 交互将陌生 Skill 目录理解为结构化 `SkillMap`。

#### Round 1 — 文件筛选

**输入**：`List[FileEntry]`（目录树 + 每文件元信息 + 前3行）

**Prompt 任务**：判断每个文件的可能角色，决定哪些文件需要完整读取。

**LLM 输出**（结构化 JSON）：
```json
{
  "files_to_read": [
    {
      "path": "relative/path/to/file",
      "suspected_role": "description | parameter_schema | implementation | dependency_ref | config | test | unknown",
      "reason": "判断依据"
    }
  ]
}
```

#### Round 2 — 组件关系建模

**输入**：Round1 指定文件的完整内容 + Round1 的角色猜测结论

**Prompt 任务**：在已知文件内容的基础上，确认角色、建立组件关系、识别入口函数、提取内嵌组件。

**LLM 输出**：完整 `SkillMap`（结构见 models 节）

---

### `comprehension/skill_map.py` — SkillMap 数据结构

`SkillMap` 是后续所有模块的共享上下文，替代原来「假设固定文件名」的 `SkillComponents`。

```
SkillMap
├── skill_root: str                    # Skill 根目录绝对路径
├── files: List[FileEntry]             # 全部文件元信息
├── role_map: Dict[path, FileRole]     # 每个文件的确认角色
├── components: List[Component]        # 逻辑组件列表（见下）
└── dependency_refs: List[str]         # 引用的外部 Skill 名称列表

Component
├── component_type: str                # description | parameter_schema | implementation
├── source_file: str                   # 来源文件路径
├── source_span: (int, int) | null     # 若从文件中提取的片段，记录行号范围
├── content: str                       # 组件实际内容
└── linked_components: List[str]       # 与本组件关联的其他 Component ID
```

关键设计：一个文件可以拆出多个 Component（如 `.md` 文件同时含描述和内嵌 Schema），Component 之间通过 `linked_components` 建立关联（如「这段描述对应这段实现」）。

---

### `core/pipeline.py` — 主流水线编排器

按序编排 7 个阶段：

```
① scanner            → List[FileEntry]
② comprehension_agent → SkillMap
③ hard_checkers      → PreflightData
④ llm_checkers       → List[Finding]
⑤ validator          → List[Finding]（过滤后）
⑥ aggregator         → List[Finding]（去重聚合）
⑦ reporter           → AuditReport JSON
```

LLM Checker 之间默认并行（`asyncio.gather`），可通过配置改为串行。

---

### `core/aggregator.py` — 缺陷聚合 & 去重

- 合并硬规则和 LLM 产出的 Finding 列表
- 基于 `(taxonomy_category, source_file, line_start)` 做去重
- 对指向同一位置的多条 Finding 合并注释

---

### `hard_checkers/schema_comparator.py` — Schema 比对器

**输入**：`SkillMap`（从中定位 `parameter_schema` 和 `implementation` 类型的 Component）

**功能**：
- 从 `implementation` Component 中提取函数签名（委托 `code_parser`）
- 将 `parameter_schema` Component 的字段声明与函数签名逐字段比对
- 检测：字段名缺失、类型不匹配、必填性冲突、返回值结构差异
- 跨 Skill 接口比对：利用 `DependencyGraph` 中依赖 Skill 的 Schema，检查上下游字段对齐

输出两类结果：高置信度直接 Finding（`hard_rule`）、结构化 diff 摘要注入 LLM prompt context。

---

### `hard_checkers/code_parser.py` — 代码静态解析器

**输入**：`implementation` 类型 Component 的内容

**提取项**：

| 提取项 | 用途 |
|---|---|
| 函数签名、参数类型注解、返回类型 | schema_comparator 比对 |
| `raise` 异常类型列表 | 与文档异常声明比对 |
| HTTP 请求 URL 字符串 | url_validator |
| 文件 I/O、全局变量写入 | 副作用判定 |
| 外部 import 列表 | dependency_extractor |
| 入口函数确认 | 校验 comprehension_agent 的判断 |

**输出**：`CodeFacts` 结构化摘要，供所有后续模块共享，避免 LLM 重复解析原始代码。

---

### `hard_checkers/dependency_extractor.py` — 依赖图提取器

**输入**：`SkillMap.dependency_refs` + `CodeFacts.imports` + 依赖声明文件（若存在）

**功能**：
- 尝试定位依赖 Skill 目录（按配置的 Skill 根目录搜索），加载其 SkillMap
- 提取依赖包名与版本约束，与本地环境比对检测版本漂移
- 构建 `DependencyGraph`：节点为 Skill，边含接口兼容性标注

**输出**：`DependencyGraph`

---

### `hard_checkers/url_validator.py` — 外部资源检查器

- 从所有 `description` 和 `implementation` Component 中正则提取 URL
- `asyncio` + `httpx` 并发 HEAD 请求验证存活性
- 404/DNS 失败 → 直接 Finding；超时 → 标注 `unverified`
- 文档 URL 和代码 URL 严重级别分开处理

---

### `hard_checkers/env_constraint_checker.py` — 环境声明冲突检查器

基于关键词规则，检测文档环境声明与代码实际行为的矛盾：

| 规则 | 文档关键词 | 代码反指标 |
|---|---|---|
| 平台冲突 | "跨平台"/"cross-platform" | `winreg`、`/proc/`、`ctypes.windll` |
| 联网冲突 | "无需联网"/"offline" | `requests`、`httpx`、`urllib` |
| 权限冲突 | "无需 root" | `os.setuid`、`sudo` |
| 无副作用冲突 | "只读"/"read-only" | 文件写入、全局变量修改 |

**输入**：`SkillMap` + `CodeFacts`

---

### `llm_checkers/base_checker.py` — LLM Checker 抽象基类

```python
def build_prompt(skill_map: SkillMap, preflight: PreflightData) -> str
def parse_response(raw: str) -> List[Finding]
def run(skill_map: SkillMap, preflight: PreflightData) -> List[Finding]
```

`preflight` 携带 `CodeFacts`、`DependencyGraph`、硬规则 Finding 列表、Schema diff 摘要，注入每个 Checker 的 prompt context，避免 LLM 重复分析已确定问题。

---

### `llm_checkers/` — 各专项 LLM Checker

| 文件 | 对应 Taxonomy | 核心审查内容 |
|---|---|---|
| `env_layer_checker.py` | 分类1：环境层 | 文档环境声明 vs CodeFacts 实际行为 |
| `doc_layer_checker.py` | 分类2：文档层 | description Component 间语义冲突、跨 Skill 接口描述冲突 |
| `impl_over_promised_checker.py` | 分类3.1：过度承诺 | schema 声明 vs CodeFacts 实现事实 |
| `impl_semantic_conflict_checker.py` | 分类3.2：语义冲突 | 参数/返回值语义、副作用、工作流顺序 |
| `impl_under_promised_checker.py` | 分类3.3：承诺不足 | 代码隐式能力 vs 文档缺失声明 |

每个 Checker 的 prompt 由 `prompts/` 对应模板填充，模板中嵌入 taxonomy 子类型定义和判定标准。

---

### `validator/criticality_validator.py` — 二次校验模块

- 对 LLM Checker 产出的每条 Finding 独立再评估是否 Critical
- 可配置为更强的模型（如用 Opus 校验 Sonnet 的产出）
- 低危承诺不足型 Finding 默认标记 `suppressed`，除非配置 `report_under_promised: true`
- 硬规则 Finding 直接跳过，以 `hard_rule` 状态进入聚合

---

### `llm_client/` — LLM 后端适配层

统一接口：
```python
def complete(prompt: str, system: str, temperature: float, max_tokens: int) -> str
```

三个实现分别对接 Anthropic SDK、OpenAI SDK、OpenAI-compatible API（通过 `base_url` 切换 vLLM/Ollama 等）。

---

### `report/reporter.py` — 报告序列化

将聚合后的 `List[Finding]` 和元数据序列化为最终 JSON 报告。

---

## 3. `config.yaml` 字段定义

```yaml
# LLM 后端配置（用于 Comprehension Agent 和 LLM Checkers）
llm:
  provider: "anthropic"            # anthropic | openai | openai_compatible
  model: "claude-sonnet-4-6"
  api_key: "${ANTHROPIC_API_KEY}"  # 支持环境变量引用
  base_url: null                   # openai_compatible 时填写
  temperature: 0.1
  max_tokens: 4096

# 二次校验模块（可配置更强模型）
validator:
  provider: "anthropic"
  model: "claude-opus-4-6"
  api_key: "${ANTHROPIC_API_KEY}"
  temperature: 0.0

# Comprehension Agent 配置
comprehension:
  max_file_size_kb: 200            # 超过此大小的文件 Round2 只读前 N 行
  first_lines_count: 3             # Round1 每文件送入的行数
  skill_roots: []                  # 依赖 Skill 的搜索根目录列表，用于跨 Skill 接口比对

# 流水线控制
pipeline:
  parallel_llm_checkers: true
  run_url_validation: true
  report_under_promised: false
  skip_checkers: []                # 可跳过指定 checker

# 硬规则子工具配置
hard_checkers:
  url_validator:
    timeout_seconds: 5
    max_concurrent: 10
  schema_comparator:
    strict_type_match: true

# 报告输出
report:
  output_path: "./audit_report.json"
  include_suppressed: false        # 是否保留被过滤的假阳性（标记状态）
```

---

## 4. 审计报告 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema",
  "title": "SkillAuditReport",
  "type": "object",
  "required": ["meta", "skill_map_summary", "summary", "findings"],
  "properties": {

    "meta": {
      "type": "object",
      "properties": {
        "skill_dir":          { "type": "string" },
        "audit_time":         { "type": "string", "format": "date-time" },
        "auditor_model":      { "type": "string" },
        "validator_model":    { "type": "string" },
        "taxonomy_version":   { "type": "string" }
      }
    },

    "skill_map_summary": {
      "type": "object",
      "description": "Comprehension Agent 的理解结果摘要，便于人工核查理解是否准确",
      "properties": {
        "total_files":        { "type": "integer" },
        "files_read":         { "type": "integer", "description": "Round2 实际完整读取的文件数" },
        "components": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "component_type": { "type": "string" },
              "source_file":    { "type": "string" },
              "source_span":    { "type": ["array", "null"] }
            }
          }
        },
        "dependency_refs":    { "type": "array", "items": { "type": "string" } }
      }
    },

    "summary": {
      "type": "object",
      "properties": {
        "total_findings":       { "type": "integer" },
        "critical_count":       { "type": "integer" },
        "high_count":           { "type": "integer" },
        "medium_count":         { "type": "integer" },
        "low_count":            { "type": "integer" },
        "suppressed_count":     { "type": "integer" },
        "agent_blocking_count": { "type": "integer",
          "description": "直接阻断 Agent 任务执行的缺陷数" }
      }
    },

    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "id", "taxonomy_l1", "taxonomy_l2", "taxonomy_l3",
          "severity", "agent_impact", "evidence",
          "rationale", "validation_status", "source_checker"
        ],
        "properties": {

          "id": { "type": "string", "description": "唯一缺陷ID，如 F-001" },

          "taxonomy_l1": {
            "type": "string",
            "enum": ["environmental", "document", "implementation"]
          },
          "taxonomy_l2": {
            "type": "string",
            "description": "二级分类，如 external_resource_invalid / interface_contract_mismatch / over_promised 等"
          },
          "taxonomy_l3": {
            "type": ["string", "null"],
            "description": "三级分类，仅 implementation 层有效，如 missing_parameter / semantic_param_conflict / implicit_param_support 等"
          },

          "severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low"]
          },

          "agent_impact": {
            "type": "object",
            "properties": {
              "blocks_execution":      { "type": "boolean" },
              "produces_silent_error": { "type": "boolean",
                "description": "不报错但结果错误" },
              "impact_description":    { "type": "string" }
            }
          },

          "evidence": {
            "type": "object",
            "description": "原文证据，精确到来源文件与行号",
            "properties": {
              "source_a": {
                "type": "object",
                "properties": {
                  "file":       { "type": "string", "description": "相对 Skill 根目录的路径" },
                  "line_start": { "type": ["integer", "null"] },
                  "line_end":   { "type": ["integer", "null"] },
                  "span_text":  { "type": "string", "description": "原文摘录" }
                }
              },
              "source_b": {
                "type": ["object", "null"],
                "description": "与 source_a 冲突的另一处证据，单来源缺陷为 null",
                "properties": {
                  "file":       { "type": "string" },
                  "line_start": { "type": ["integer", "null"] },
                  "line_end":   { "type": ["integer", "null"] },
                  "span_text":  { "type": "string" }
                }
              }
            }
          },

          "rationale": {
            "type": "string",
            "description": "判定理由：为何认定此处为不一致，及属于该 taxonomy 子类型的依据"
          },

          "validation_status": {
            "type": "string",
            "enum": ["confirmed", "suppressed", "hard_rule"],
            "description": "confirmed=LLM二次校验通过；suppressed=假阳性或低危过滤；hard_rule=硬规则直接产出"
          },

          "source_checker": {
            "type": "string",
            "description": "产出该 Finding 的模块名"
          }
        }
      }
    }
  }
}
```

---

## 5. 各硬规则子工具功能设计

### `schema_comparator`
- **输入**：`SkillMap`（定位 schema/impl Component）+ `CodeFacts`
- 逐字段比对 schema 声明 vs 函数签名：字段名、类型、必填性、返回结构
- 跨 Skill 上下游接口字段对齐检查（依赖 `DependencyGraph`）
- 高置信度差异 → 直接 Finding；低置信度差异 → 生成 diff 摘要注入 LLM prompt

### `code_parser`
- **输入**：`implementation` Component 内容（Python AST 解析）
- 提取函数签名、异常列表、HTTP URL、I/O 操作、全局写入、import 列表
- 输出 `CodeFacts` 结构化摘要，全局共享，避免 LLM 重复读原始代码

### `dependency_extractor`
- **输入**：`SkillMap.dependency_refs` + `CodeFacts.imports`
- 定位依赖 Skill 目录，加载其 SkillMap 提取接口声明
- 检测 Python 包版本漂移（`importlib.metadata` vs 声明约束）
- 输出 `DependencyGraph`

### `url_validator`
- 从所有 Component 中正则提取 HTTP/HTTPS URL
- `asyncio` + `httpx` 并发 HEAD 请求，带超时
- 404/DNS → 直接 Finding；超时 → `unverified` 标注
- 代码中 URL 比文档中 URL 严重级别高一档

### `env_constraint_checker`
- **输入**：`SkillMap` + `CodeFacts`
- 关键词规则匹配文档声明 vs 代码反指标（平台、联网、权限、副作用）
- 匹配即产出高置信度 Finding，不送 LLM

---

## 6. 模块调用关系

```
main.py
  └─► pipeline.py
        │
        ├─[①]─► scanner.py
        │           └─ 返回 List[FileEntry]（路径/大小/扩展名/前3行）
        │
        ├─[②]─► comprehension_agent.py
        │           ├─ Round1: List[FileEntry] → LLM → files_to_read
        │           ├─ 按需加载指定文件完整内容
        │           ├─ Round2: 文件内容 + Round1结论 → LLM → SkillMap
        │           └─ 返回 SkillMap（全局共享）
        │
        ├─[③]─► hard_checkers/（部分并发，部分有依赖顺序）
        │           │
        │           ├─ code_parser.py          → CodeFacts
        │           │       ↑ 依赖 SkillMap 定位 impl Component
        │           │
        │           ├─ dependency_extractor.py → DependencyGraph
        │           │       ↑ 依赖 SkillMap + CodeFacts
        │           │
        │           ├─ schema_comparator.py    → List[Finding] + diff_summary
        │           │       ↑ 依赖 SkillMap + CodeFacts + DependencyGraph
        │           │
        │           ├─ url_validator.py        → List[Finding]
        │           │       ↑ 依赖 SkillMap（独立，可与上方并行）
        │           │
        │           └─ env_constraint_checker.py → List[Finding]
        │                   ↑ 依赖 SkillMap + CodeFacts
        │                         │
        │                   合并为 PreflightData = {
        │                     skill_map, code_facts, dep_graph,
        │                     hard_findings, diff_summary
        │                   }
        │
        ├─[④]─► llm_checkers/（默认并行，共享 PreflightData）
        │           ├─ env_layer_checker.py
        │           ├─ doc_layer_checker.py
        │           ├─ impl_over_promised_checker.py
        │           ├─ impl_semantic_conflict_checker.py
        │           └─ impl_under_promised_checker.py
        │                     ↑ 各自调用 llm_client/（按 config 选择后端）
        │
        ├─[⑤]─► criticality_validator.py
        │           ├─ 输入：LLM Checker 产出的 List[Finding]
        │           ├─ 调用 llm_client/（可配置更强模型）
        │           └─ 输出：带 validation_status 的 List[Finding]
        │
        ├─[⑥]─► aggregator.py
        │           ├─ 合并 hard_findings + validated_llm_findings
        │           ├─ 按 (taxonomy_category, source_file, line_start) 去重
        │           └─ 返回最终 List[Finding]
        │
        └─[⑦]─► reporter.py
                    └─ 序列化 AuditReport JSON → 写入 output_path
```

**关键数据流约定**：

1. `SkillMap` 是全局共享上下文，由 Comprehension Agent 产出，传入所有后续模块，取代硬编码文件名假设。
2. `CodeFacts` 是代码的结构化摘要，由 `code_parser` 产出，注入所有 LLM Checker 的 prompt，避免 LLM 直接读原始代码。
3. `PreflightData.diff_summary` 是 schema 比对器的结构化差异，作为 LLM Checker 的前置上下文，避免重复比对。
4. 硬规则 Finding 不经过 `criticality_validator`，直接以 `hard_rule` 状态进入聚合。
5. `DependencyGraph` 的构建依赖 `CodeFacts`（获取 import 列表），因此 `code_parser` 必须先于 `dependency_extractor` 完成。
