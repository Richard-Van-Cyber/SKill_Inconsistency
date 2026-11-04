# Motivating Example —— 左文档 / 右代码，序号标注

> 用途：Introduction 末尾 / Section 2。配套 Figure 1（`motivation_figure.tex`）。

## 图：左右两栏 + 序号

```
┌─ (a) the document ────────┐   ┌─ (b) the code ───────────────┐
│ ①  :3   "…D3.js (v6)."    │   │                              │
│ ①  :75  "default:         │   │                              │
│          d3@7.9.0."       │   │                              │
│                           │   │                              │
│ ②  :59  "Sort input rows  │   │ ② bubble_chart_example.js:62 │
│          deterministically│   │     const sectors =          │
│          …"               │   │     [...new Set(data.map(    │
│     :60  "…Array.from(    │   │     (d => d.sector))];       │
│          grouped.keys())  │   │     // no sort               │
│          .sort()"         │   │     // 另一个示例 :73 反而排了 │
│                           │   │                              │
│ ③  :68  "If a force layout│   │ ③ bubble_chart_example.js:56 │
│          is required: …   │   │     d3.forceSimulation(data) │
│          fix the tick     │   │     // default ticks,        │
│          count, …run      │   │     // no seed               │
│          exactly N ticks" │   │                              │
└───────────────────────────┘   └──────────────────────────────┘
```

**编号的读法**：同一个序号标出**一条不一致性的两端**；两端落在哪个盒子里，就决定了它是什么 boundary。

| 序号 | boundary | 两端 |
|---|---|---|
| **①** | Document–Document | 两端都在左栏（`SKILL.md:3` ↔ `:75`） |
| **②** | Document–Code | 左 `SKILL.md:59–60` ↔ 右 `bubble_chart_example.js:62` |
| **③** | Document–Code | 左 `SKILL.md:68–71` ↔ 右 `bubble_chart_example.js:56` |

②有一个额外的加分事实：这个 skill 的**另一个**示例 `interactive_table_example.js:73` 是排了序的——
也就是说**它自己发的两个示例互相矛盾**。

## 正文

An Agent Skill is a directory an agent loads as instructions. It has two sides: a `SKILL.md` contract written for the reader, and the scripts that are supposed to carry it out. The agent cannot execute the contract to see whether it holds. It reads the text and acts on it. We take one Skill from the SkillBench corpus we audit in Section [§corpus] and read its contract the way an agent would.

Figure 1 puts the document on the left and the code on the right, and numbers every inconsistency at both of its ends. The boxes those ends sit in name its boundary. Both ends on the left is a document--document inconsistency; one end on each side is a document--code inconsistency.

The first defect has both ends in the document. Line 3 of `SKILL.md` describes the Skill as producing visualizations "with D3.js (v6)". Line 75 instructs the reader to pin D3 to "a specific version (default: `d3@7.9.0`)", and the next line recommends vendoring `d3.v7.9.0.min.js`. One file, two major versions of its own central dependency.

The second and third cross from the document into the code, and both are determinism rules that the shipped example breaks. Lines 59--60 require the reader to "sort input rows deterministically before binding to marks" and to use a "stable grouping order (explicit `Array.from(grouped.keys()).sort()`)". `bubble\_chart\_example.js:62` builds its sector grouping as `[...newSet(data.map(d => d.sector))]`, which keeps the input order. The Skill's other example does sort its rows (`interactive\_table\_example.js:73`), so the two shipped examples disagree with each other as well.

The third defect is the same shape. Lines 68--71 state that if a force layout is required the reader must "fix the tick count, fix initial positions deterministically" and "run exactly N ticks and stop". `bubble\_chart\_example.js:56` builds a default `d3.forceSimulation(data)`: a tick count nobody sets, initial positions nobody fixes, and no seed. An agent that copies the example inherits a layout the contract forbids.

All three are settled by opening the two boxes, before any agent runs, and all three are instances of the types we define in Section [§taxonomy].

**Observation 1.** *The boundary is a property of the artifacts, not a label we assign.* The version is contradicted inside one file; the two determinism rules are contradicted across two. Neither is a documentation-style problem: link checkers, linters and doc builds all pass on this Skill. RQ1 asks which kinds of contract inconsistency occur in real Skills, how often, and how they distribute across the boundaries.

**Observation 2.** *Reading the artifacts tells you what is inconsistent, not what an agent will do about it.* Both determinism rules are stated as requirements, and both are broken silently: an unsorted grouping and a default force layout both draw a perfectly plausible chart, only not the same one twice. An agent may follow the rules, ignore them, or never read them, and the artifacts do not say which. RQ2 asks whether these inconsistencies can be found automatically, and whether the ones an agent will build on can be separated from the ones it will read past.

**Observation 3.** *They are not equally repairable.* Correcting the version is a one-token edit once someone decides which line to trust. Correcting either determinism rule means changing a layout or a sort and accepting that the picture will move, and the two fixes land in different places: one in the grouping code, one in the simulation setup. Repair therefore has to be evaluated per defect, not per Skill. RQ3 asks what each kind of inconsistency costs an agent, and whether repairing it recovers that cost.

---

## 为什么第三条也是 doc–code

你原来想要三种类型，但左右两栏版式里没有 environment 的位置。这一版按你的要求
"第一个例子用文档内版本、第二个用 doc–code、第三个再找一个"，
第三条我选了**另一条 doc–code**（force layout 的 tick 数/初值/seed 那条），理由：

- 它与②是**两条不同的规则、两处不同的代码**（`:59–60` 对 `:62`；`:68–71` 对 `:56`），不是同一条缺陷重复计。
- 都是我逐行核过的。

如果你要第三格是 **Skill–Environment**，得在图里加第三块区域（放在右栏外侧，画成"文档指向环境"的箭头）；
代价是会重新引入上一轮你担心的"①③ 共享版本号"问题。要的话我加。

## 排版实测

| | 结果 |
|---|---|
| 图 | **13.57 × 7.31 cm**（左右并排，宽而矮），0 error / 0 overfull |
| 正文 | **textwidth 8–16cm 全部 0 error / 0 overfull** |

注意：图 13.57cm 宽，**双栏会议（IEEE 单栏约 8.4cm）放不下**，需要用 `figure*` 跨栏，
或者只在单栏版面用。
