# adv/02 · offer-letter-generator —— 条件块的跨段切分

**状态**：**已完成四步**（对抗数据 → OriginalSkill 触发验证 → 修复 → RepairedSkill 对比）
**判定**：**L1 ✓ 触发 / L2 ✓ 归因 / L3 ✓ 修复规避**。
代价：修复臂中位 token 148k → 173k（**+17%**），即这一处修复是**用 token 换可靠性**。

---

## 一、被验证的不一致性

`docx/SKILL.md` 给出的"条件段落处理"参考实现，要求 `{{IF_X}}` 与 `{{END_IF_X}}`
落在**同一段落**内：

```python
for para in doc.paragraphs:
    text = para.text
    if start_marker in text and end_marker in text:   # ← 必须同段
        ...
        para.runs[0].text = new_text                  # ← 只写回第一个 run
        for run in para.runs[1:]:
            run.text = ''
```

而真实公文模板里，条件块**天然跨段**：标记可能分别落在不同段落。
一旦跨段，`if` 永不成立 → 标记被原样写进产物。

## 二、① 对抗性任务数据

`data/offer_letter_template.adv.docx`（生成脚本 `evidence/build_adv_template.py`）：
把 `{{IF_RELOCATION}}` / `{{END_IF_RELOCATION}}` **拆到第 27 / 28 两个段落**，
做法是在 "This includes" 处做 run 级切分。其余（金额、天数、占位符）保持出厂一致。

## 三、② OriginalSkill 触发验证（3 trial，对抗数据）

| cell | status | score | 残留 `{{IF…}}` | 残留 `{{END_IF…}}` | amount/days 保留 |
|---|---|---|---|---|---|
| O r1 | graded | 1.000 | ✗ | ✗ | ✓ / ✓ |
| **O r2** | **verifier_error** | **—** | ✗ | **✓** | ✓ / ✓ |
| O r3 | graded | 1.000 | ✗ | ✗ | ✓ / ✓ |

### L1 触发 ✓
O r2 的产物里 `{{END_IF_RELOCATION}}` **原样残留**，verifier 无法解析 → `verifier_error`。
即原臂 **1/3** 被该不一致性打中。

### L2 归因 ✓
残留的正是**结束标记**、而开始标记被清掉 —— 与"只处理了含开始标记的那一段"的
预测完全一致：跨段后 `if` 条件不成立，开始标记所在段被别处逻辑处理掉，结束标记无人处理。
若只是"忘了替换占位符"，两个标记应同时残留。

### L3 修复规避 ✓
修复把"同段判定"改成**前向扫描**：从含开始标记的段落起向后累积，直到拼出的文本
包含结束标记，再整体处理（include 则拼接后写回首段、其余段清空；exclude 则整块清空）。
修复臂 **3/3** 干净（无任何残留标记），`score` 全 1.000。

## 四、代价（本协议要求同时报告）

| 口径 | OriginalSkill | RepairedSkill | 变化 |
|---|---|---|---|
| 有效 cell | 2/3 graded（r2 verifier_error） | 3/3 graded | +1 cell |
| score（含把 verifier_error 记为失败） | 0.667 | **1.000** | +0.333 |
| api_calls（中位） | 7 | 8 | +1 |
| total_tokens（中位） | 148k | 173k | **+17%** |

修复替换了参考实现的主体循环，属于"新增/改写代码路径"，因此**不满足** P13 的
"净删除"结构 —— 它换来的可靠性提升是真实的（1/3 的失败率），但 token 成本上升了。
这正是 P13 预言的情形：**改写代码块方向的修复，成本不确定，必须实测。**

## 五、复现

```bash
cd experiments/adv02-offer-20260924
# 数据 / 修复 / 证据
python3 <repo>/adv/02-offer-letter-generator/evidence/build_adv_template.py
# 实验（服务器）
~/anonymous/.venv-benchflow/bin/python3 runner-source/adv_run.py --workers 3
# 判定
python3 <repo>/analysis_tools/offer_conditional_analyze.py experiments/adv02-offer-20260924
```

原始记录：`experiments/adv02-offer-20260924/analysis.json`、`runs/`。
