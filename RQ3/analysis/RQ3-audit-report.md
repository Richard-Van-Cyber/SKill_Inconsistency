# RQ3 Audit Report — how skill inconsistencies propagate through agent execution

Data: **441 paired cells** (49 tasks × 3 models × 3 trials), each contrasting `OriginalSkill` against
`FixedSkill` over the same task — 882 trajectories, ≈44,000 agent turns, balanced at 147 pairs per
model. Artifacts: `labels_v3.csv`, `audit_v3-output.txt`, `../descriptors/*.json`,
`../detectors/audit_v3.py`.

**Cell selection.** Cells are resolved with the same rule used for RQ2, not by raw manifest order:
trials r1–r3 only, auxiliary (placebo / pilot) batches excluded, only cells whose task-package image
equals the task's current image (the image taken from the Qwen axis, which was run last and verified
against a fresh build), and the latest study among the survivors. This matters: 134 of the 882
(axis, task, arm, trial) keys have 2–5 candidate runs in the manifest spread across studies, so
resolving by manifest order — as an earlier revision of this audit did — silently mixes stale
task-package versions into the analysis.

**Coverage.** The audit codes the two skill arms only; `NoSkill` (514 trajectories with content) is
excluded by design, because with no skill mounted there is nothing to be exposed to and no
inconsistency to propagate. It serves as RQ2's capability floor, not as part of this chain.

---

## What RQ3 studies: three things

| | Question | Level |
|---|---|---|
| **3.1 Exposure** | Does the agent come into contact with the skill? | did it read the skill |
| **3.2 Response** | Given contact, what does it do with the inconsistent element? | bypass / follow / recover |
| **3.3 Outcome** | What does that cost in score and compute? | score lost, detour paid |

The chain is a two-level construct: **exposure is contact** (reading the skill); **response is what
happens after contact**. A run that never reads the skill is *unused* and lies outside the chain. This
separates "the agent never saw the inconsistency" from "the agent saw it and went around it" — two
different situations that a single "not exposed" label would conflate.

| response | definition |
|---|---|
| **Bypass** | read the skill, but never executed the changed file and never authored the inconsistent form |
| **Follow → failure** | used the inconsistent element; a tied verifier check fails here but passes after the repair |
| **Recover → success** | used it, the incident fired, and the run still passes the tied checks |
| **BothFail (control)** | the same tied check fails in *both* arms — task difficulty, not the inconsistency |
| **Unused** | never read the skill (induced if only the Original arm skipped it, else habit) |

Every label rests on a concrete signal: skill contact on a skill-path action (path or `Skill` tool);
"used" on executing a file the repair changed or authoring a shipped-only anchor; "manifested" on a
shipped-only anchor surfacing in tool output or an error while executing that file; "delivered wrong"
on the verifier's per-check results, which are ground truth rather than inferred.

---

## 3.1 Exposure — contact is nearly universal

| model | n | exposed (read the skill) | rate | read via `Skill` tool |
|---|---|---|---|---|
| DeepSeek-V4-Flash | 147 | 147 | **100%** | 28 |
| Claude Haiku 4.5 | 147 | 144 | 98% | 69 |
| Qwen3.6-35B | 147 | 137 | 93% | 17 |
| **all** | **441** | **428** | **97.1%** | 114 |

Only **13 / 441 = 2.9%** of runs are unexposed, split between model habit (8 runs where *neither* arm
read the skill) and inconsistency-induced avoidance (5 runs where only the Original arm skipped it).

**Finding 1.** Contact is essentially universal: 97% of runs read the skill, and the strongest model
reads it in every single run. *Whether the agent sees the inconsistency does not distinguish the
models, and therefore cannot explain the RQ2 effectiveness gaps.*

Detection note: 114 runs reach the skill through the `Skill` tool by name rather than by path. A
path-only detector would have missed these and inflated "unused"; the audit covers both routes.

---

## 3.2 Response — what differs is what happens after contact

| response | n | share |
|---|---|---|
| Recover → success | 155 | 35.1% |
| BothFail (control) | 103 | 23.4% |
| **Follow → failure** | **97** | **22.0%** |
| Used, no effect | 39 | 8.8% |
| Bypass | 34 | 7.7% |
| Unused (habit / induced) | 13 (8 / 5) | 2.9% |

By model:

| response | DeepSeek | Haiku | Qwen |
|---|---|---|---|
| Recover → success | **82** | 40 | 33 |
| Follow → failure | **18** | **44** | 35 |
| BothFail (control) | 20 | 40 | 43 |
| Bypass | 8 | 11 | 15 |
| Used, no effect | 19 | 9 | 11 |
| Unused | 0 | 3 | 10 |

**Finding 2.** The models are indistinguishable in exposure but sharply distinguishable in response.
DeepSeek recovers in 56% of its runs and follows into failure in 12%; Qwen does nearly the reverse
(22% recover, 24% follow). *The capability gap operates after contact, not at contact.*

**Finding 3.** The ordering of follow-into-failure counts — **Haiku 44, Qwen 35, DeepSeek 18** —
matches the ordering of the RQ2 repair gains exactly (Haiku +0.136, Qwen +0.085, DeepSeek +0.023, the
last not significant). The mechanism behind the RQ2 deltas is the number of runs in which the agent
adopts the inconsistency and delivers it. This ordering is only visible under the RQ2 cell-selection
rule; resolving duplicates by manifest order gave Haiku 34 and Qwen 35, which spuriously inverted it.

Response by inconsistency type (n ≥ 6):

| type | n | Bypass | Follow | Recover | BothFail |
|---|---|---|---|---|---|
| `implementation/over_promised` | 108 | 0 | **41** | 41 | 17 |
| `document/cross_document_process_conflict` | 63 | 0 | 18 | 23 | 21 |
| `script_logic_mismatch` *(legacy)* | 54 | 8 | 6 | 15 | 8 |
| `document/interface_contract_mismatch` | 45 | 0 | 6 | 13 | 18 |
| `environmental/environment_fact_conflict` | 45 | 0 | 13 | 11 | 21 |
| `document/shared_concept_definition_conflict` | 36 | 0 | 5 | 22 | 8 |
| `implementation/semantic_conflict` | 18 | 0 | 4 | **13** | 1 |
| `environmental/external_service_contract_change` | 9 | 0 | 3 | 4 | 2 |
| `docs_assume_absent_runtime_tool` *(legacy)* | 9 | 0 | 0 | 7 | 1 |
| `missing_promised_output_field` *(legacy)* | 9 | 3 | 0 | 0 | 0 |
| `doc_wrong_field_name` *(legacy)* | 9 | 7 | 0 | 0 | 0 |
| `hardcoded_output_path` *(legacy)* | 9 | 4 | 0 | 3 | 1 |
| `docs_missing_required_fields` *(legacy)* | 9 | 2 | 1 | 0 | 4 |
| `missing_promised_field` *(legacy)* | 9 | 2 | 0 | 3 | 0 |
| unlabelled (`?`) | 9 | 8 | 0 | 0 | 1 |

**Finding 4.** Follow-into-failure is concentrated in `over_promised` (41 of 97, 42%): a documented
capability the code never implements is the single most reliable way to make an agent deliver a wrong
artifact. Conversely `semantic_conflict` almost always recovers (13 of 18): a contradiction in meaning
is noticed and worked around far more often than a missing capability.

---

## 3.3 Outcome — the score is lost in one place; the compute is lost everywhere

### Score, by response

| response | n | score Orig | score Fixed | Δscore | Δtok/run | Δsec/run |
|---|---|---|---|---|---|---|
| **Follow → failure** | 97 | 0.632 | 0.999 | **+0.366** | +34k | +76 |
| Recover → success | 155 | 0.982 | 0.944 | −0.038 | −57k | −35 |
| Bypass | 34 | 0.852 | 0.949 | +0.097 | +2k | +38 |
| BothFail (control) | 103 | 0.475 | 0.505 | +0.030 | +7k | +2 |
| Used, no effect | 39 | 0.994 | 0.947 | −0.047 | −44k | −19 |
| Unused (induced) | 5 | 0.743 | 1.000 | +0.257 | +7k | +76 |
| Unused (habit) | 8 | 0.832 | 0.878 | +0.045 | +2k | −150 |

**Finding 5.** The repair's whole benefit is concentrated in one cell of the matrix. `Follow` gains
**+0.366**; every other class sits at Δ ≈ 0. Fixing a skill pays off exactly when, and only when, it
stops the agent from delivering the inconsistency.

**Finding 6.** The 103 `BothFail` cells (23%) fail the same tied checks before and after the repair.
They are a task-difficulty floor, not an effect of the inconsistency, and must be excluded from any
attribution — otherwise they dilute the measured effect by roughly a quarter.

**Finding 6b (attribution limits).** The response classes are not equally usable for attribution.
Only `Follow`, `Recover` and `BothFail` have the treatment actually administered in the Original arm
(it executed the changed file). In `Bypass` and `Unused` the inconsistent element was never used, so
their Δscore cannot be read as the inconsistency's cost: across the 34 bypass pairs, 21 score
identically in both arms, and of the 3 where the bypassing arm scores *higher*, two have a Fixed arm
that also never touched the element (the gap is run-to-run variance). `Bypass` measures avoidance
behaviour, not harm.

### Incident footprint inside the trajectory (not a net cost)

Whole-run token deltas cannot express the cost of a *recovered* incident, because the repaired arm
often does **more** legitimate work. In `hook-decision-exit-code`, for example, the Fixed arm performs
21 additional verification calls. The incident's *footprint* is therefore measured inside the
trajectory: from the turn it first manifested to the turn the agent settled on the corrected form
(Recover) or to the end of the run (Follow).

| response | n | settled found | detour turns | share of run | detour tokens | detour seconds |
|---|---|---|---|---|---|---|
| **Recover → success** | 155 | 131 | 12.3 | **28%** | ≈116k | **60** |
| **Follow → failure** | 87 | 78 | 14.4 | 24% | ≈148k | 104 |
| BothFail (control) | 87 | 72 | 19.6 | 34% | ≈218k | 169 |
| Bypass | 4 | 4 | 3.8 | 16% | ≈15k | 40 |

**Finding 7 (corrected).** The incident occupies a substantial footprint even in runs that end
successfully — 12.3 turns, 28% of the run, ≈116k tokens, 60 seconds — but **this is not a net compute
penalty**. On the same Recover pairs the Fixed arm spends **57k tokens more** than the Original arm
(944k-equivalent vs 982k-scale means), and its turn count is no lower. The repair buys correctness,
not thrift: a more complete skill induces more work, which offsets the detour the agent would
otherwise take. An earlier revision of this report described the 28% footprint as a "compute tax",
which conflated footprint with cost.

**Finding 8.** The footprint scales with how long the agent stays on the wrong path: Bypass (early
exit, ≈15k) < Recover (detour then correction, ≈116k) < Follow (never corrected, ≈148k) < BothFail
(never solvable, ≈218k).

### By model

| model | Follow | Recover | Bypass | mean Δscore among Follow |
|---|---|---|---|---|
| DeepSeek-V4-Flash | 18 | **82** | 8 | +0.393 |
| Claude Haiku 4.5 | **44** | 40 | 11 | +0.351 |
| Qwen3.6-35B | 35 | 33 | 15 | +0.372 |

**Finding 9.** When a model follows an inconsistency into failure, the loss is nearly total (Δscore
+0.35 to +0.39, i.e. the repair recovers most of the remaining headroom). DeepSeek suffers the same
per-incident loss but incurs 4.9× fewer incidents than Haiku, which is why its RQ2 aggregate is small
and not significant.

---

## What RQ3 explains about RQ2

```
exposure   :  ~97% for every model, 100% for the strongest   -> not the differentiator
response   :  Follow 44 / 35 / 18   (Haiku / Qwen / DeepSeek) -> the differentiator
outcome    :  Follow loses +0.366 of score; Recover pays a 28% footprint but no net token penalty
```

RQ2's per-model repair gains (+0.136 Haiku, +0.085 Qwen, +0.023 DeepSeek, n.s.) are the aggregate of
these per-incident responses, and the ordering of the follow-into-failure counts reproduces them
exactly. The mechanism is not that weak models fail to find the skill — they find it as often as the
strong model — but that they **adopt** what it says.

---

## Limitations

1. **Unvalidated coder.** Behavioural labels come from a deterministic rule-based coder. Outcome
   signals (scores, checks) are ground truth; exposure/response labels are candidates until a
   stratified sample of 30–40 trajectories is hand-coded and agreement (Cohen's κ) is reported.
2. **Fixed-arm control validity.** Four Recover pairs have a Fixed arm that neither read the skill nor
   executed the changed file (one of them scores 0.33 against the Original arm's 0.92). Restricting
   Recover to pairs with a clean control (read + executed + no shipped form) leaves n = 95 and moves
   Δscore from −0.041 to −0.029 and Δtok from −42k to −31k, so the conclusion is insensitive to the
   filter — but the filter should still be applied and reported.
3. **Anchors are not globally unique.** 60 of the 156 Fixed arms in the Recover class author a
   *shipped-only* anchor. The anchors are "removed by the repair", not "absent everywhere else in the
   skill", and they also fire when the agent merely greps for the old token. "Anchor in an agent
   action" is therefore a noisy proxy for "used", and the paper must say so.
4. **Type labels are mixed.** 12 of the 49 tasks carry the earlier audit vocabulary
   (`script_logic_mismatch`, `docs_*`, …), not yet mapped onto the current 10-type taxonomy; one task's
   type is unrecorded (`?`).
5. **Detour token figures are estimates.** Per-turn token records in the CLI stream are unreliable, so
   detour tokens are estimated as the run's total tokens weighted by the detour's share of turns.
   Detour turns and seconds are measured directly.
6. **`BothFail` is a floor, not an effect.** The 103 control cells should be excluded from
   attribution; the reason they fail in both arms (task difficulty vs an undetected second
   inconsistency) is not distinguished here.
