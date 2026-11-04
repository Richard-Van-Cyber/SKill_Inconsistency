# Artifact — Skill contract inconsistencies in Agent Skills

This artifact accompanies the paper *When Do Skill Inconsistencies Matter?
Understanding Their Runtime Impact on LLM Agents*. It contains the auditor
`SkillAudit`, the taxonomy it implements, the analysis that produces the RQ1
statistics, the experiment harness and analysis for the runtime study (RQ2), and
the exposure/response analysis that traces a static inconsistency to a runtime
outcome (RQ3).

210 files, 2.6 MB. The tree is organised by research question, in the order the
paper presents them.

| path | role |
|---|---|
| `skill-audit/` | `SkillAudit`: the static auditor and the layered taxonomy |
| `paper_audit_reports/rq1_analysis/` | RQ1 statistics: prevalence, density, types, domain distribution |
| `paper_audit_reports/skillbench_verification/` | the manual validation that yields the ground-truth finding set |
| `experiments/` | the RQ2 runtime study and its run harness |
| `analysis_tools/` | exposure, impact and trajectory analysis for RQ2/RQ3 |
| `RQ3/` | the detectors that trace exposure → response → consequence |
| `paper_audit_reports/motivation_figure/` | the motivating example of Section 2 |
| `inconsistency_taxonomy.md` | the taxonomy in narrative form |

---

## SkillAudit and the taxonomy (Section 4)

The taxonomy has three artifact boundaries:

| layer | what disagrees |
|---|---|
| **Environmental** | the Skill vs. the runtime environment |
| **Inter-document** | two descriptive documents of the same Skill |
| **Document–code** | documentation vs. the implementation it describes |

`skill-audit/` implements it as four sequential modules sharing one intermediate
representation:

| module | code |
|---|---|
| Package Comprehension — a scanner plus a two-round LLM agent that builds the `SkillMap`, cached by content hash | `comprehension/scanner.py`, `comprehension/comprehension_agent.py` |
| Inconsistency Detection — four deterministic checkers (AST code analysis, schema comparison, environment-constraint checking, execution-path URL validation) and five LLM checkers, one per taxonomy class | `hard_checkers/` (`code_parser.py`, `schema_comparator.py`, `env_constraint_checker.py`, `url_validator.py`), `llm_checkers/` |
| Adjudication and Aggregation — *confirmed* / *suppressed* verdicts with adjusted severity and evidence strength, fail-open, then exact-key deduplication and semantic clustering into root causes | `validator/criticality_validator.py`, `core/aggregator.py` |
| Reporting — JSON and Markdown findings carrying a taxonomy label, severity, line-numbered evidence, rationale, evidence strength and impact class | `report/reporter.py`, `report/md_reporter.py` |

Entry point `skill-audit/main.py`; configuration template
`skill-audit/config.example.yaml`; checker prompts in `skill-audit/prompts/`;
taxonomy label maps in `skill-audit/core/heuristic_map.py`; finding schema in
`skill-audit/models/finding.py`. `skill-audit/WORKFLOW.md` documents the actual
execution path of every stage.

---

## RQ1 — Characterizing skill contract inconsistencies

The pipeline reads the audit reports and rebuilds every statistic in the paper,
in steps that match the subsections of the RQ.

| step | code | produces |
|---|---|---|
| build the per-Skill table: contract claims, documentation and code claims, line counts, file composition | `rq1_analysis/build_dataset.py` | one row per Skill |
| **Prevalence and Density** — share of Skills with at least one inconsistency, per-Skill count mean/median/P90, inconsistencies per 100 contract claims | `rq1_analysis/analyze_prevalence.py` | prevalence and density tables, count distribution |
| **Types** — distribution over the taxonomy at level 1 and level 2 | `rq1_analysis/analyze_types.py` | type and artifact-boundary tables |
| **Distribution across skill domains** — heterogeneity over the eight domains | `rq1_analysis/analyze_cooccurrence.py`, `rq1_analysis/make_category_figure.py` | co-occurrence and domain tables |
| figures | `rq1_analysis/make_figures.py` | the RQ1 figures |

`rq1_analysis/rq1_lib.py` holds the shared definitions: taxonomy maps, the
contract-claim counter (documentation statements plus documented code
interfaces), corpus colours and plotting style. `run_all.sh` runs the sequence
and writes `outputs/` and `figures/`. The `outputs/` directory already carries
the emitted tables, in both CSV and LaTeX.

The corpora are named **GitHub** and **SkillBench** in the paper. Inside the
code and the result files the GitHub corpus carries the key `wildskills`, its
collection directory name; the mapping is one-to-one.

### Ground-truth validation

`paper_audit_reports/skillbench_verification/` re-checks the findings
independently and rewrites every RQ1 table on the validated basis:

| step | code |
|---|---|
| verify that each cited evidence span exists where the finding places it | `verify_evidence.py` |
| assemble the validation payload per finding | `build_verify_input.py` |
| aggregate independent verdicts (*confirmed* / *mislabeled* / *invalid*) with reason codes | `aggregate_verification.py` |
| rewrite every RQ1 table and figure on the validated basis | `apply_verification.py`, `make_verified_figures.py` |

`outputs/verified/` holds the verified tables.

---

## RQ2 — Runtime impact of skill inconsistencies

Every task runs under three conditions — **NoSkill**, **Original**, **Fixed** —
with three trials per condition, each unit graded by the task verifier.

| part | code |
|---|---|
| harness: agent launch, container setup, dependency preparation, verifier invocation | `experiments/*/runner-source/` (`run_agents.py`, `wildskills_run.py`, `rq3_cli_runner.py`, `rq3_cli_proxy.py`, `rq3_support.py`, `verifier_dependencies.py`, `wildskills_config.py`) |
| the 49-task study | `experiments/wildskills49-gptoss-20261002/` — `run_gptoss.sh`, and `tools/paper_stats_all_axes.py`, `tools/aggregate_axis.py`, `tools/build_manifest_all_axes.py`, `tools/make_report.py` |
| the three-model study | `experiments/wildskills25-20261001/` — `paper_stats.py`, `final_three_axis.py`, `three_axis.py`, `aggregate_axis.py` |
| **Effectiveness** — verifier check-pass fraction per condition and the paired per-task difference | emitted by the statistics scripts above |
| **Efficiency** — token and wall-clock cost per condition | `analysis_tools/impact_ranking.py`, `analysis_tools/make_impact_report.py`, `analysis_tools/section4.py` |
| failure classification and error families | `analysis_tools/classify_failures.py`, `analysis_tools/arm_error_families.py` |

`analysis_tools/impact_ranking.py` ranks audited packages by the impact of their
inconsistencies on task completion, token cost and wall-clock cost;
`analysis_tools/make_impact_report.py` renders that ranking.

---

## RQ3 — When and why do inconsistencies matter?

RQ3 traces static inconsistency → exposure → agent response → runtime
consequence. Each link has its own detector under `RQ3/detectors/`.

| link | code | what it decides |
|---|---|---|
| **Exposure** | `RQ3/detectors/exposure_strict.py`, `analysis_tools/exposure_scan_baseline.py` | whether a run reached the Skill's content at all, separating content access from merely listing the directory, and the path route from the `Skill` tool route |
| **Agent response** | `RQ3/detectors/recover_detail.py`, `RQ3/detectors/recover_strict.py`, `RQ3/detectors/bypass_detail.py` | what the agent did on meeting the defect — recovered, bypassed, or never noticed |
| **Runtime consequence** | `RQ3/detectors/audit_v3.py`, `RQ3/detectors/verify_fix_cells.py` | the per-cell cost, and whether the repair arm is a valid control |
| **Batch execution and validation** | `RQ3/detectors/run_batch.py`, `RQ3/detectors/detect_case.py`, `RQ3/detectors/llm_validate.py`, `RQ3/detectors/show_skill_tool.py` | runs the detectors over a study and validates their verdicts |

`analysis_tools/trace_forensics.py` reconstructs the agent's ordered action
stream per run and reports the error and recovery profile;
`analysis_tools/trace_causal_report.py` and
`analysis_tools/make_trace_report.py` turn it into the causal verdicts the paper
cites. `analysis_tools/parse_baseline_runs.py` normalises the baseline runs;
`analysis_tools/refresh_all.sh` rebuilds the derived tables in dependency order.
`analysis_tools/skillsbench_traj_mine.py` mines the SkillBench trajectories for
the signals those scripts consume.

`RQ3/build_descriptors.py` and `RQ3/verify_repair_principles.py` build the task
descriptors and check that each repair honours the repair principle;
`RQ3/paper/make_fig_response_type.py` draws the response-type figure and
`RQ3/paper/rq3-section.tex` holds the section source.

---

## Motivating example (Section 2)

`paper_audit_reports/motivation_figure/`:

| file | what |
|---|---|
| `motivation_figure_sessionB_fixed.tex` | the figure: document on the left, code on the right, one coloured frame per inconsistency |
| `motivation_figure.tex` | the same figure built from `fit` nodes rather than explicit coordinates |
| `motivation_section.tex` | the surrounding text and the three observations |
| `analyse_case.py` | per-defect engagement: whether the defect reaches an agent's own reasoning or code, for two models |
| `preview.tex` | standalone preamble used to render the figure |
| `MOTIVATION_CAPTIONS.md` | caption variants and the verified evidence table behind each inconsistency |
| `MOTIVATION.md`, `MOTIVATION_SECTION.md` | working notes on the case selection and the section wording |

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
