# Motivating example — the three inconsistencies (English, for the figure)

All spans below were checked by hand against
`tasks/data-to-d3/environment/skills/d3-visualization/`.
Skill directory: 4 files — `SKILL.md` plus three scripts under `scripts/`.

---

## Variant A — detailed (default, put in the figure caption)

> **Figure 1:** Three contract inconsistencies in one real Skill,
> `d3-visualization`; the document is on the left, the code it ships is on the
> right, and each coloured frame encloses **both ends** of one inconsistency, so
> the frame's horizontal span shows the boundary at which the contract breaks.
>
> **① inter-document.** The same `SKILL.md` names two major versions of its own
> central dependency. Line 3 describes the Skill as building visualizations
> "with D3.js **(v6)**"; line 75 pins "a specific version (default:
> **d3@7.9.0**)", and line 76 recommends vendoring `vendor/d3.v7.9.0.min.js`.
> Both ends sit in the document, 72 lines apart, and nothing else in the Skill
> says which one holds.
>
> **② document–code.** Lines 59–60 require the reader to "**sort** input rows
> deterministically before binding to marks" and to use a "stable grouping order
> (explicit `Array.from(grouped.keys()).sort()`)". `bubble_chart_example.js`
> never sorts. It builds the sector list at line 62 and the colour-scale domain
> at line 41 from `[...new Set(data.map(d => d.sector))]`, so both follow the
> input row order. The Skill's *other* example does sort its rows
> (`interactive_table_example.js:73`); the two shipped examples therefore
> disagree with each other as well.
>
> **③ document–code.** Lines 68–71 are conditional and binding: "If a force
> layout is required: fix the tick count, fix initial positions
> deterministically, run exactly N ticks and stop." `bubble_chart_example.js:56`
> builds a bare `d3.forceSimulation(data)`. It sets no tick count, no seed and no
> initial positions — none of the three required actions is taken.
>
> All three are settled by reading the two files, before any agent runs, and
> none of them raises an error when the Skill is used.

---

## Variant B — medium (~140 words)

> **Figure 1:** Three contract inconsistencies in one real Skill,
> `d3-visualization`; the document is on the left, the code it ships on the
> right, and each coloured frame encloses both ends of one inconsistency.
> **①** The same `SKILL.md` names two major versions of its own dependency:
> line 3 says "D3.js **(v6)**" while line 75 pins "**d3@7.9.0**" and line 76
> recommends vendoring `d3.v7.9.0.min.js` — both ends in one file, 72 lines
> apart. **②** Lines 59–60 require deterministic sorting and a "stable grouping
> order (explicit `Array.from(grouped.keys()).sort()`)"; `bubble_chart_example.js`
> never sorts, building its sector list (line 62) and colour domain (line 41)
> from `[...new Set(...)]` and so following the input row order. **③** Lines
> 68–71 require that a force layout fix the tick count, fix initial positions and
> run exactly N ticks; line 56 builds a bare `d3.forceSimulation(data)` and does
> none of the three. All three are visible from the files, and none raises an
> error at run time.

---

## Variant C — compact (~80 words, if the caption must stay short)

> **Figure 1:** Three contract inconsistencies in one real Skill,
> `d3-visualization`; each frame encloses both ends of one inconsistency.
> **①** `SKILL.md:3` names "D3.js (v6)" while `:75` pins "d3@7.9.0" — the same
> file, two major versions, 72 lines apart. **②** `:59–60` require sorted, stable
> grouping; `bubble_chart_example.js:62` builds `[...new Set(...)]` and never
> sorts. **③** `:68–71` require a force layout to fix its tick count and initial
> positions; `:56` uses a bare `d3.forceSimulation(data)`. None of the three
> raises an error at run time.

---

## In-figure one-liners (already used as the grey comments)

| # | text inside the frame |
|---|---|
| ① | `// one file, two contradictory major versions` |
| ② | `// the row order must be stable and explicit` |
| ③ | `// layout output must be reproducible` |

Alternatives that state the violation more directly:

| # | alternative |
|---|---|
| ① | `// the same file names v6 and v7.9.0` |
| ② | `// the rule says sort; this example never does` |
| ③ | `// the rule says fix the count and the seed; this example fixes neither` |

---

## Verified evidence table

| # | boundary | document side | code side | silent? |
|---|---|---|---|---|
| ① | inter-document | `SKILL.md:3` `with D3.js (v6)` vs `:75` `default: d3@7.9.0`, `:76` `vendor/d3.v7.9.0.min.js` | — (both ends in the document) | yes |
| ② | document–code | `SKILL.md:59` `**Sort** input rows deterministically before binding to marks`; `:60` `stable grouping order (explicit Array.from(grouped.keys()).sort())` | `bubble_chart_example.js:62` `const sectors = [...new Set(data.map(d => d.sector))];` and `:41` `.domain([...new Set(data.map(d => d.sector))])` — no `sort` anywhere in the file | yes |
| ③ | document–code | `SKILL.md:68–71` `If a force layout is required: fix the tick count, fix initial positions deterministically, run exactly N ticks and stop.` | `bubble_chart_example.js:56–59` `d3.forceSimulation(data)` with centre/collide/charge forces; no `.tick()`, no `.stop()`, no `randomSource` anywhere in the file | yes |

**Cross-check for ②:** the Skill's other shipped example *does* sort —
`interactive_table_example.js:73` `data.sort((a, b) => {` — so the two examples
contradict each other, not just the rule.

---

## Two qualifications to keep honest

1. **② is a divergence from the stated rule, not run-to-run instability.**
   `new Set` preserves insertion order and `d3.csv` preserves file order, so for a
   *fixed* input the example is deterministic. What it is not is independent of
   the input's row order: the same sectors in a different order yield different
   colours (`:41`) and different cluster anchors (`:62`), which is precisely what
   the "sort before binding" rule exists to prevent. Do not write "the chart
   changes on every run" — that would be wrong.

2. **③ is the stronger of the two, because its rule is conditional and its
   condition is met.** The document says "if a force layout is required …", the
   example does use a force layout, and it performs none of the three required
   actions. Whether d3's defaults are themselves non-deterministic is a separate
   question; the inconsistency is that the contract names three specific
   obligations and the shipped artifact honours none of them.
