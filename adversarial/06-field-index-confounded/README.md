# 06 · 字段索引（pivot field index）—— **有 reward 差异，但机制归因失败（混杂）**

**目标不一致性**：`sales-pivot-analysis` 的 `xlsx/SKILL.md` 把同一个索引 1 赋予两种语义：

```
第181行:  # Field 1: ProductName - not used (just include it)
第234行:  pivot.pivotFields[1] = PivotField(axis="axisCol", showAll=False)  # Quarter = col
```

而任务的 `SourceData` 里 `Quarter` 是**追加列**（在 `STATE` 与收入列之后），索引 1 不可能是它。
按文档照抄 `pivotFields[1]` 就会把错的字段设成列轴。

verifier 对 "State Income Quartile" 表有精确断言：
`assert col_field and "quarter" in actual_col.lower()`。

## 实验（treatment = 技能文档，同一份出厂数据，各 3 trial）

| 条件 | 各次 score | 平均 |
|---|---|---|
| OriginalSkill | 0.0 / 1.0 / 0.0 | **0.333** |
| RepairedSkill | 1.0 / 1.0 / 1.0 | **1.000** |

修复只改了一处：把二维透视表示例里写死的索引改成**按 cache field 名字查索引**
（`fld = {f.name: i for i, f in enumerate(pivot.cache.cacheFields)}`）。

**看上去是一次干净的大成功（0.333 → 1.000，+0.667）。但机制归因不成立。**

## 为什么不成立

### (1) 没有任何一次运行用到那个索引

| cell | score | 调用 pivot API 次数 | 出现的字面索引 |
|---|---|---|---|
| OriginalSkill r1 | 0.0 | **0** | — |
| OriginalSkill r2 | 1.0 | 131 | `RowColField(x=2)`, `(x=6)`, `(x=7)` |
| OriginalSkill r3 | 0.0 | **0** | — |
| RepairedSkill r1/r2/r3 | 1.0 | 16 / 4 / 12 | — |

**`pivotFields[1]` 一次都没出现过。** 两次失败是 `pivotAPI = 0` ——
verifier 报的是 `IndexError: list index out of range`（`workbook[sheet]._pivots[0]` 不存在），
即 **agent 根本没建任何透视表对象**，只写了普通表格/数值。

### (2) 失败点根本不在列字段

- `OriginalSkill__r1`：四个 sheet 的 `_pivots` 全为空 → 结构性缺失。
- `OriginalSkill__r3`：`Missing POPULATION_2023 column`、`Invalid quarter values: {'Unknown'}`
  → SourceData 内容错误。

两条都与"列字段是不是 quarter"无关。

### (3) 真正的自变量是**文档可执行性**，不是不一致性

修复后的示例给出了完整的"查名字 → 设 axisRow/axisCol/dataField → append row/col/data field"流程，
原示例则是一堆带 `# Quarter = col` 注释的硬编码索引。数据上表现为：
**修复臂 3/3 都真正调用了 pivot API，原臂有 2/3 完全没调用。**

这是我改动文档时无意引入的**第二个自变量**（可执行性），
它与目标不一致性（索引语义冲突）**共线**，因此这次实验无法把效果归给后者。

## 教训（新增 P8）

> **修复必须是单变量的。** 只改目标不一致性那几行；一旦顺带让示例"更完整/更可运行"，
> 就把"文档可执行性"这个更强的自变量混了进来，效果无法归因。

本案例的两个对照臂在**文档可执行性**上差异过大，因此尽管 reward 差异很大（+0.667），
**不能**声称"修复字段索引提高了成功率"。

要把它做成可归因的实验，需要**第三个臂**：
只把 `pivotFields[1]` 改成 `pivotFields[<正确索引>]`，其余一字不动（保持原示例的完整度）。
这样两臂的差异才只有索引本身。

## 文件

| 文件 | 内容 |
|---|---|
| `repair/SKILL.original.md` | 原 `xlsx/SKILL.md` |
| `repair/SKILL.repaired.md` | 我的修复（**引入了可执行性混杂**） |
| `evidence/analysis.json` | 6 个 cell 的 score / pivot API 调用次数 / 字面索引 |
| `evidence/pivot_fieldindex_analyze.py` | 分析脚本 |
