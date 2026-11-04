# Motivating Example —— 客观现象版（v6）

> 修订要点：**Figure 1 只讲客观现象**，不含任何实验臂（NoSkill/OriginalSkill/RepairedSkill），
> 也不含模型对比——那些属于 Evaluation，放在 RQ2/RQ3 的结果图里。
> 旧的双模型矩阵图另存为 `fig_engagement_matrix_results.tex`（结果章用）。

---

## 1. 案例（客观事实，逐条可核对）

`d3-visualization`（SkillBench 任务 `data-to-d3` 自带的 Skill），**一个契约里同时存在 3 处不一致**，
分属 taxonomy 的三个不同位置，且**不需要跑任何 agent 就能确认**：

| # | 不一致 | 类型（复核后） | 证据（文件:行） |
|---|---|---|---|
| **D1** | 同一份文档给出两个 D3 版本 | `document / shared_concept_definition_conflict`（high） | `SKILL.md:3` `…with D3.js (v6).` ↔ `SKILL.md:75` `Pin D3 to a specific version (default: d3@7.9.0).` |
| **D2** | 承诺的联动调用了一个无人定义的函数 | `document / interface_contract_mismatch`（high） | `interactive_table_example.js:6` 承诺 `Two-way highlighting (click table row → highlight chart element)`；`:107` 调 `highlightBubble(ticker)`——**全目录 grep 不到任何定义** |
| **D3** | 强制确定性，随附示例不满足 | `implementation / over_promised / missing_constraint_or_exception`（medium） | `SKILL.md:70` `fix initial positions deterministically, … run exactly N ticks and stop.` ↔ `bubble_chart_example.js:56` `d3.forceSimulation(data)`（默认、无 seed） |

三处均已通过独立复核（`verification_results.csv` 判定 confirmed / mislabeled-修正后仍是实现层）。

---

## 2. 图

| 图 | 文件 | 放哪 | 内容 |
|---|---|---|---|
| **Figure 1** | `motivation_figure.tex` ｜ `motivation_preview.png/.pdf` | **Introduction** | 一个 Skill、三处不一致，逐条给出"文档说 X / 制品是 Y"，箭头后直接挂 taxonomy 标签；无任何实验内容 |
| Figure R（结果） | `fig_engagement_matrix_results.tex` | RQ2/RQ3 | 3 缺陷 × 2 模型 × 9 run 的触达矩阵 + 行为与代价对比 |

Figure 1 的三段：(a) 技能目录 + 三处不一致（红底标违约片段，右侧内联 taxonomy 标签）；
(b) 一句话收敛"现象"：**这个契约自相矛盾、让读者调用不存在的函数、并且自己违反自己强制的规则；
读它的人无法判断该信哪一条**。全部可在跑 agent 之前读完文件确认。

---

## 3. 三条 Observation（由现象推出，各自引出一个 RQ）

> **Observation 1 — A Skill's contract can be inconsistent with itself, not only with its code.**
> The `d3-visualization` contract names two different D3 versions in two of its own lines, and
> documents a two-way highlight that its own example implements by calling a function no file
> defines. These are not exotic corner cases: they are the first two things a reader of this Skill
> encounters. *This raises a descriptive question: how often are real Skill contracts internally
> inconsistent or at odds with what they ship, and which kinds dominate?* → **RQ1.**

> **Observation 2 — Such inconsistencies are cheap to see statically but impossible to rank by reading.**
> All three defects above are visible without running anything, yet they are not equivalent: one is a
> version disagreement the reader can resolve by looking at the vendored bundle, one is a call that
> silently does nothing, and one is a requirement the shipped example violates. Nothing in the
> artifacts says which of them matters. *This raises a detection question: can we find these
> inconsistencies automatically, and separate the ones that change what an agent builds from the ones
> it walks past?* → **RQ2.**

> **Observation 3 — Whatever an agent does with such a defect, it pays.**
> A reader who notices the version conflict must decide which of the two statements to trust; a reader
> who does not notice inherits the conflict into its deliverable. One path spends effort on
> resolution, the other ships a silently defective artifact, and the two costs look nothing alike.
> *This raises an impact question: how much does each inconsistency actually cost an agent, and does
> repairing it pay off?* → **RQ3.**

（三条都不依赖实验结果：①②③ 是"读文件可得"的事实与由其自然产生的问题；
"哪种代价更大"留给 RQ2/RQ3 回答——这正是全文要做的。）

---

## 3b. 尺寸：默认是"窄而高"，另有"宽而矮"备选

| 文件 | 版式 | 实测尺寸 | 适用 |
|---|---|---|---|
| **`motivation_figure.tex`**（现行） | **窄而高**：引文换行，taxonomy 标签另起一行右对齐 | **8.2 cm × 11.2 cm** | 单栏、图旁还要放文字时 |
| `motivation_figure_wide_alt.tex` | 宽而矮：标签内联在 → 行右侧 | 10.4 cm × 9.0 cm | 想要横向铺开、少占纵向空间时 |

两者内容、包依赖完全相同（tikz + xcolor，都不需要 amssymb），改 `\input` 的文件名即可切换。
两个文件都实测 0 error / 0 overfull。

宽度旋钮仍然是 `\motw`（pane 的文字宽度，图总宽 = 该值 + 12pt）：

```latex
\newlength{\motw}\setlength{\motw}{7.8cm}   % 现行：总宽约 8.2cm
```

窄版**不要**把 `\motw` 调大——引文是手动断行的，调大只会右侧留白；要更宽就用 wide 备选。

## 3c. 旧的旋钮说明（仅供参考）

`motivation_figure.tex` 里只有一处控制宽度：

```latex
\newlength{\motw}\setlength{\motw}{10.0cm}   % 图的总宽 = 这个值 + 12pt
```

| `\motw` | 图总宽 | 说明 |
|---|---|---|
| 14.35cm（旧） | ≈ 14.9cm | 几乎满栏 |
| **10.0cm（现行）** | **≈ 10.4cm** | 比原来窄约 30%，字号不变 |
| 9.0cm | ≈ 9.4cm | 实测仍不折行，是安全下限 |
| < 9.0cm | — | 右侧的 taxonomy 标签会折行 |

**为什么不是 `\resizebox`**：`\resizebox{\linewidth}{!}{...}` 或 `transform shape` 会把字号一起缩小
（\scriptsize 从 7pt 掉到 5–6pt，印出来看不清）。这里的做法是**只缩容器、不缩字体**：
把 pane 的 `text width` 调小，并把三条过长的行手动断行、把三个"→"结论短语改短，
所以 10.0cm 与 9.0cm 下都是 0 error / 0 overfull。

若你用的是导出的 PDF 而不是 TikZ 源码，那就简单了：
`\includegraphics[width=0.7\linewidth]{motivation_preview.pdf}`。

## 4. 关于"强模型触发更多"——这是结果图的口径问题，不是动机图的结论

你指出得对：如果按"被触达的运行数"来画，看起来就像"强模型更容易受影响"。
**这个读法是错的，我在结果图里改了表述**：

| 易被误读 | 正确表述 |
|---|---|
| "D3 被 deepseek 触达 9/9、被 haiku 触达 0/9 → 强模型更受影响" | 方块统计的是**缺陷是否进入了 agent 自己的推理/代码**，即"它是否不得不处理这件事"。 |
| 触达 = 受害程度 | **触达 ≠ 受害**：notice 的模型付出**解决成本**（deepseek 为 D1 与文档争论、9/9 撞到 API budget）；不 notice 的模型付出**静默缺陷成本**（haiku 把 D2 那个未定义的调用直接抄进代码、8/9 自称完成却 0/9 得分）。 |
| "强模型被契约带偏" | 恰恰相反：deepseek 的原话是 *"The skill says pin d3@7.9.0, but the task explicitly requires D3 v6…"*——它在**对抗**契约，不是被它骗。 |

所以结果图 (b) 的标签已改为 **"did the agent have to deal with the defect?"**，
图例注明"filled = 该缺陷进入了 agent 自己的推理或代码——它要么解决了它，要么照抄了它"，
caption 也明说"这不是受害程度的度量"。这样两栏读起来就是**代价类型不同**，而不是"谁被影响更多"。

---

## 5. 复现

```bash
cd paper_audit_reports/motivation_figure
python3 analyse_case.py data-to-d3     # 触达矩阵的原始统计（engaged / exposed / untouched）
tectonic -X compile preview.tex        # 编译 Figure 1
```

## 6. 局限

- 触达指标是**文本代理**：符号出现在 agent 自己写的块里即算触达，未区分"提及"与"据此改变产出"。
- 每模型每臂 3 run（共 18），只作定性对比，不做显著性主张。
- 结果图的 D2 有 1/3 的 haiku 阳性来自 NoSkill 臂，故不借 D2 做强断言。
