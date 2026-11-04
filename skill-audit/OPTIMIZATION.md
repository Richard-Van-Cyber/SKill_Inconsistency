# skill-audit 优化说明（2026-09-22）

本次只改静态检测工具本身，不改任务、不改 verifier、不引入新数据源。
所有结论都有可复现命令；`python3 tests/test_regressions.py` 覆盖核心行为。

## 一、改动前后对照（用既有 10 份产出实测）

| 指标 | 改前 | 改后 |
|---|---|---|
| 硬规则 finding 总数（10 任务） | 29 | **1** |
| 其中 url_validator | 27（全部为参考链接/示例地址） | 0（lenient 模式下不报） |
| env_constraint_checker | 2（均为误报） | 1（low / speculative，已降级） |
| schema_comparator | 0（220 行未工作） | 可工作（见测试 §3） |
| validator LLM 调用（10 任务） | 172 | 每批 12 条一次，预计 ≈20 |
| 报告指标 | 只有 finding 条数 | 条数 + **根因数** + 证据强度 + 确认阻断数 |
| 正常模式可运行性 | 并行/串行 checker 路径会因 `llm_findings` 未初始化而崩 | 已修（见 §三 #2） |
| comprehension 缓存 | 不可用（键不稳定） | 可用（键只随 skill 内容变化） |
| 错误路径 | 目录不存在 → "0 缺陷"退出 0 | 非零退出并说明原因 |
| 无凭据时 | 直接崩 | `--dry-run` 可跑确定性层 |

## 二、逐项改动

### 1. 坏路径不再伪装成"审计通过"（P0）
`comprehension/scanner.validate_skill_root()`：路径不存在 / 不是目录 / 无 SKILL.md → `SkillRootError`；
`main.py` 捕获后返回退出码 2。改前传一个错路径会得到 `0 findings` 并退出 0。

### 2. URL 检查：只查"会被执行"的 URL（P0）
- `code_parser._parse_http_urls` 排除 docstring —— 文档字符串里的 URL 是散文不是调用；
- 新增 `code_parser.classify_doc_urls`，把 URL 分成「命令行实际调用」与「文档引用」；
- `url_validator` 新增 `mode`（`off` / `lenient` 默认 / `strict`）与 `code_urls` 入参；
- `localhost`、`127.0.0.1`、私有地址、`*.example.com`、`target.com` 等一律跳过（`skipped_example_urls()` 可查看）；
- **文档类 URL 永不再标 `blocks_execution`**（最高 low）。配置：`hard_checkers.url_validator.mode`。

### 3. schema_comparator 从零产出改为可用
- 入口函数选择要求"有参数"，并优先使用 `if __name__ == "__main__"` 的实测调用（`module_entry_calls`）；
- 按"与 schema 参数名的交集"排序选择目标函数；**删除 `next(iter(...))` 兜底**；
- 参数名无交集时**跳过并记录原因**，不再把每个参数都报成 over-promised；
- 修好 markdown 参数表解析（按表头取列、跳过 `| --- |` 行），此前会把表头 `param` 当成参数；
- `code_parser` 现在给每个函数带上 `source_file`，证据可定位。

### 4. 去重：精确键 + 语义根因聚类
- `core/aggregator.py` 重写：先精确去重，再按「同锚点」或「证据 token Jaccard ≥ 阈值」聚类；
- 输出 `root_cause_id` 与 `contributing_checkers`（同一缺陷被多个 checker 报出时记录全部）；
- 未确证（`confidence != verified`）的"阻断执行"声明会被降级，不再靠合并放大；
- 报告同时给出 `raw_finding_count` 与 `root_causes`。

> 注：既有 10 份产出只压缩 14%，因为它们是旧 prompt 产生的——`line_start` 全是 `null`。
> 新 prompt 要求填真实行号后，同锚点合并才会生效。

### 5. LLM 检查：可锚定 + 受控词表
- `base_checker._format_skill_content` 给每行加行号前缀，并明确要求填 `line_start`；
- 新增 `taxonomy_l2` 归一化表（`unimplemented_feature`/`missing_return_field` → `over_promised` 等），
  跨 checker 的同一缺陷才能聚合；
- 新增 `confidence`（verified / inferred / speculative）与 `agent_impact.impact_class`
  （verified / may_block_if / silent / cosmetic），5 个 prompt 同步更新。

### 6. validator 批量化 + 职责分离
- 每批 12 条一次调用（改前每条一次：172 次调用、suppress 0 条）；
- 规则抑制（`under_promised`）与模型判负分开计数（`suppressed_by_rule`）；
- 被 suppress 的条目不再保留"阻断执行"。

### 7. 韧性
- comprehension 3 次指数退避重试；失败抛出可读错误而非原始 traceback；
- comprehension 结果按目录内容哈希缓存（`pipeline.cache_dir`，默认 `./.audit-cache`），可 `--no-cache`；
- `main.py` 把配置缺失/格式错误、凭据失败、审计失败分别映射到退出码 2 / 2 / 1。

### 8. dry-run（无凭据回归测试）
`--dry-run` 跳过 LLM 阶段；无缓存时用 `core/heuristic_map.build_heuristic_map` 从文件构造粗略
SkillMap（md → description，py/js/sh → implementation，含 name 列的表 → parameter_schema）。
这让确定性层可独立测试——也解释了为什么改前确定性层几乎无产出：它完全依赖 comprehension
抽出的 components，而 url_validator 是唯一会自己重扫文件文本的检查器。

### 9. 报告
JSON 与 Markdown 增加：`root_causes`、`by_confidence`、`contributing_checkers`、
`impact_class`、`preflight`（入口函数、函数数、schema diff、各 checker 产出、是否 dry-run）。
Markdown 概览新增"证据强度"一行与提示语：**只有 `confidence=verified` 且 `blocks_execution=true`
才表示已确认会导致执行失败**。

## 三、验证过程中新发现并修掉的 bug

用两套测试（`tests/test_regressions.py`、`tests/test_integration_stubs.py`）压出来的问题：

| # | 问题 | 现象 | 修复 |
|---|---|---|---|
| 1 | `core/pipeline.py` 漏 `import json` | 写 comprehension 缓存时 `NameError` | 补导入 |
| 2 | `llm_findings` 未在所有分支初始化 | 并行/串行 checker 路径 `UnboundLocalError`（**正常模式直接崩**） | 在分支前统一初始化 |
| 3 | 缓存键把 `__pycache__/*.pyc` 算进去 | Python 每次重写 pyc → 键每次都变 → 缓存 0 命中 | 只哈希可审计文件（复用 scanner 的忽略规则） |
| 4 | 缓存键包含自己的输出与缓存目录 | 第二次运行把报告写进被审计目录 → 键变化 → 仍然 0 命中 | 支持排除路径/子树；macOS 上 `resolve()` 与 `abspath()` 不同（`/var`→`/private/var`），统一用 `realpath` |
| 5 | URL 阻断判定用文件后缀 | 代码字面量的 source 记为组件类型而非文件名，`source.endswith(".py")` 恒假 → **真阻断被降级** | 改为显式标记 `executed_in_code` |
| 6 | `impact_class` 用 `may_block_if` 表示代码内阻断 | 与语义不符 | 代码内阻断改为 `verified` |

其中 #2、#3、#4、#5 都是**只有在写测试时才会暴露**的问题——这也说明原工具没有测试（`tests/` 是空目录）本身就是这个风险。

## 四、验证命令

```bash
# 回归测试（无需 API）
python3 tests/test_regressions.py

# 确定性层，10 个任务（无需 API）
for t in civ6-adjacency-optimizer court-form-filling crystallographic-wyckoff-position-analysis \
         data-to-d3 dialogue-parser energy-market-pricing fix-druid-loophole-cve \
         fix-erlang-ssh-cve grid-dispatch-operator mario-coin-counting; do
  python3 main.py --skill-dir ../selected_tasks/$t/environment/skills \
                  --dry-run --output /tmp/dry_$t.json
done

# 坏路径必须失败
python3 main.py --skill-dir /tmp/not-a-skill --output /tmp/x.json ; echo "exit=$?"   # 期望 2
```

## 五、有意没做（需要你确认后再动）

1. **`task_contract_checker`**：把 `task.md` / verifier 的硬约定与 skill 声明交叉比对。
   它能覆盖审计完全漏检的 5 类"任务专属机制"，但会把工具从"只看 skill 目录"变成
   "需要任务输入"，超出"静态检测工具"的范围，所以留给你决定。
2. **`config.yaml` 里的明文 API Key**：改成 `${PENGUIN_API_KEY}` 需要你确认由哪个环境变量提供、
   以及那把 key 是否要轮换（我没有替你做这个决定，也没有写入任何新密钥）。
3. **`url_validator` 的 `strict` 模式**：会把死链按 low 报出来。默认关（`lenient`），
   因为本批实验中它们是纯噪声。
