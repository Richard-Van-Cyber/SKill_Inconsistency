# Artifact — Skill contract inconsistencies in Agent Skills

This artifact accompanies the paper *When Do Skill Inconsistencies Matter?
Understanding Their Runtime Impact on LLM Agents*. It contains the auditor
(`SkillAudit`), the taxonomy it implements, the analysis that produces the RQ1
statistics, the experiment harness and analysis for the runtime study (RQ2), and
the exposure/response analysis that traces a static inconsistency to a runtime
outcome (RQ3).

The code is organised by research question, in the order the paper presents them.

| path | what it implements |
|---|---|
| `skill-audit/` | `SkillAudit`: the static auditor and the layered taxonomy |
| `paper_audit_reports/rq1_analysis/` | RQ1 statistics: prevalence, density, types, domain distribution |
| `paper_audit_reports/skillbench_verification/` | the independent manual validation that yields the ground-truth finding set |
| `experiments/` | RQ2/RQ3 experiment drivers and the run harness |
| `analysis_tools/` | runtime-exposure, impact and trajectory-forensics analysis |
| `RQ3/` | RQ3 detectors: exposure, agent response, consequences |
| `adversarial/`, `adv/` | constructed defect-exposing cases |
| `paper_audit_reports/motivation_figure/` | the motivating example of Section 2 |

---

## SkillAudit and the taxonomy (Section 4)

The taxonomy has three artifact boundaries:

| layer | what disagrees |
|---|---|
| **Environmental** | the Skill vs. the runtime environment |
| **Inter-document** | two descriptive documents of the same Skill |
| **Document–code** | documentation vs. the implementation it describes |

`skill-audit/` implements it as four sequential modules sharing one
intermediate representation:

| module | code |
|---|---|
| Package Comprehension — scanner plus a two-round LLM agent that builds the `SkillMap`, cached by content hash | `comprehension/scanner.py`, `comprehension/comprehension_agent.py` |
| Inconsistency Detection — four deterministic checkers (AST code analysis, schema comparison, environment-constraint checking, execution-path URL validation) and five LLM checkers, one per taxonomy class | `hard_checkers/` (`code_parser.py`, `schema_comparator.py`, `env_constraint_checker.py`, `url_validator.py`), `llm_checkers/` |
| Adjudication and Aggregation — *confirmed* / *suppressed* verdicts with adjusted severity and evidence strength, fail-open, then exact-key deduplication and semantic clustering into root causes | `validator/criticality_validator.py`, `core/aggregator.py` |
| Reporting — JSON and Markdown findings carrying a taxonomy label, severity, line-numbered evidence, rationale, evidence strength and impact class | `report/reporter.py`, `report/md_reporter.py` |

Entry point: `skill-audit/main.py`; configuration template:
`skill-audit/config.example.yaml`. The prompts the LLM checkers use live in
`skill-audit/prompts/`, the taxonomy label maps in
`skill-audit/core/heuristic_map.py`, and the finding schema in
`skill-audit/models/finding.py`.

---

## RQ1 — Characterizing skill contract inconsistencies

The RQ1 pipeline reads the audit reports and rebuilds every statistic in the
paper, in three steps that match the three subsections of the RQ.

| step | code | produces |
|---|---|---|
| Build the per-Skill table: contract claims, documentation and code claims, lines, file composition | `rq1_analysis/build_dataset.py` | one row per Skill |
| **Prevalence and Density** — share of Skills with ≥1 inconsistency, per-Skill count mean/median/P90, inconsistencies per 100 contract claims | `rq1_analysis/analyze_prevalence.py` | prevalence and density tables, the count-distribution figure |
| **Types** — distribution over the taxonomy, at level 1 and level 2 | `rq1_analysis/analyze_types.py` | type tables and the boundary figure |
| **Distribution across skill domains** — heterogeneity across the eight domains | `rq1_analysis/analyze_cooccurrence.py`, `rq1_analysis/make_category_figure.py` | co-occurrence tables, domain figure |

`rq1_analysis/rq1_lib.py` holds the shared definitions: the taxonomy maps, the
contract-claim counter (documentation statements plus documented code
interfaces), the corpus colours and the plotting style. `run_all.sh` runs the
whole sequence and writes `outputs/` and `figures/`.

The two corpora are named **GitHub** and **SkillBench** throughout the paper.
Inside the code and the result files the GitHub corpus carries the key
`wildskills`, because that is the directory name it was collected under; the
mapping is one-to-one.

### Ground-truth validation

The paper reports results on a manually validated subset. That validation is
reproducible in four steps under
`paper_audit_reports/skillbench_verification/`:

| step | code |
|---|---|
| Verify that every cited evidence span exists where the finding says it does | `verify_evidence.py` |
| Assemble the validation payload per finding | `build_verify_input.py` |
| Aggregate the independent verdicts (*confirmed*, *mislabeled*, *invalid*) with reason codes | `aggregate_verification.py` |
| Rewrite every RQ1 table and figure on the validated basis | `apply_verification.py`, `make_verified_figures.py` |

---

## RQ2 — Runtime impact of skill inconsistencies

Experiments run each task under three conditions — **NoSkill**, **Original**,
**Fixed** — with three trials per condition, and grade every unit with the
task's verifier.

| part | code |
|---|---|
| Run harness shared by all studies: agent launch, container setup, dependency preparation, verifier invocation | `experiments/*/runner-source/` (`run_agents.py`, `rq3_cli_runner.py`, `verifier_dependencies.py`, `wildskills_config.py`) |
| Three-condition comparison on a common basis (one observation per experimental unit, placebo and pilot batches excluded) | `experiments/wildskills25-20261001/final_three_axis.py`, `experiments/wildskills25-20261001/three_axis.py` |
| Paper statistics for the three-model study | `experiments/wildskills25-20261001/paper_stats.py`, `experiments/wildskills25-20261001/aggregate_axis.py` |
| Effectiveness — the verifier's check-pass fraction per condition, and the paired per-task difference | emitted by the scripts above |
| Efficiency — token and wall-clock cost per condition | same scripts, plus `analysis_tools/impact_ranking.py` |

`analysis_tools/impact_ranking.py` ranks the audited packages by the impact of
their inconsistencies on task completion, token cost and wall-clock cost;
`analysis_tools/make_impact_report.py` renders that ranking.

---

## RQ3 — When and why do inconsistencies matter?

RQ3 traces the chain static inconsistency → exposure → agent response →
runtime consequence. Each link has its own detector under `RQ3/detectors/`.

| link | code | what it decides |
|---|---|---|
| **Exposure** | `RQ3/detectors/exposure_strict.py`, `analysis_tools/exposure_scan_baseline.py` | whether a run reached the Skill's content at all, separating *content access* from merely listing the directory, and the path route from the `Skill` tool route |
| **Agent response** | `RQ3/detectors/recover_detail.py`, `RQ3/detectors/bypass_detail.py`, `RQ3/detectors/recover_strict.py` | what the agent did on meeting the defect — recovered, bypassed, or never noticed |
| **Runtime consequence** | `RQ3/detectors/audit_v3.py`, `RQ3/detectors/verify_fix_cells.py` | the per-cell cost and whether the repair arm is a valid control |
| **Batch execution and validation** | `RQ3/detectors/run_batch.py`, `RQ3/detectors/llm_validate.py`, `RQ3/detectors/detect_case.py`, `RQ3/detectors/show_skill_tool.py` | runs the detectors over a study and validates their verdicts |

`analysis_tools/trace_forensics.py` reconstructs the agent's ordered action
stream per run and reports the error/recovery profile;
`analysis_tools/trace_causal_report.py` and `analysis_tools/make_trace_report.py`
turn it into the causal verdicts the paper cites. `analysis_tools/refresh_all.sh`
rebuilds the derived tables in dependency order.

Constructed defect-exposing cases — the ones that make an otherwise dormant
defect reachable — are under `adversarial/` (eight cases) and `adv/`. Each case
carries the builder that constructs the stimulus, the evidence script that
measures the effect, and, where applicable, the reference repair.

---

## Motivating example (Section 2)

`paper_audit_reports/motivation_figure/` contains the figure source and the
analysis behind it:

| file | what |
|---|---|
| `motivation_figure_sessionB_fixed.tex` | the figure: document on the left, code on the right, one coloured frame per inconsistency |
| `motivation_section.tex` | the accompanying text |
| `motivation_figure.tex` | earlier layout of the same figure |
| `analyse_case.py` | per-defect engagement: whether the defect reaches an agent's own reasoning or code, for two models |
| `MOTIVATION_CAPTIONS.md` | the caption variants and the verified evidence table |

---

## Running the code

```bash
# 1. audit a skill package
cd skill-audit
cp config.example.yaml config.yaml
export DEEPSEEK_API_KEY="..."          # the config loader substitutes ${VAR}
python3 main.py --help

# 2. RQ1 artefacts
cd paper_audit_reports/rq1_analysis
bash run_all.sh

# 3. RQ3 derived tables
bash analysis_tools/refresh_all.sh
```

`rq1_analysis/` resolves its inputs and outputs relative to the script. The
experiment drivers, and the three analysis scripts that reconstruct study paths
(`skillbench_verification/verify_evidence.py`,
`skillbench_verification/build_verify_input.py`,
`motivation_figure/analyse_case.py`), read the workspace root from a constant at
the top of the file; point that constant at your own copy before running them.
