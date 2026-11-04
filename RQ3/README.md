# RQ3 — how skill inconsistencies propagate into agent behaviour

RQ1 asks *what* inconsistencies exist, RQ2 *how much* they cost, RQ3 *through what process* they
produce those costs. This directory holds the instrument for RQ3, built on the trajectories of the
same 49 tasks × 3 models × 3 trials × (Original, Fixed) that RQ2 summarises.

## Layout

```
RQ3/
├── build_descriptors.py      # task package  ->  one inconsistency descriptor per task
├── descriptors/              # 49 JSON descriptors + ../descriptors.csv (summary)
├── detectors/
│   ├── detect_case.py        # label ONE paired case (task, model, trial)
│   └── run_batch.py          # label every paired cell -> analysis/labels.csv
├── analysis/
│   ├── labels.csv            # 450 labelled paired cells (current manifest)
│   └── label_*.json          # per-case signatures + labels + evidence
└── logs/
```

## The chain we measure

```
inconsistency type  ->  was it used during execution?  ->  how did the agent respond?  ->  outcome
                         (exposure)                        (response, paired)             (score, cost)
```

Three rules keep this from collapsing into "type -> consequence":

1. **Use, not mention.** Anchor occurrences are counted separately in *agent-authored* actions
   (Bash commands, Write/Edit payloads) and in *tool results* (file contents, command output).
   Only the former — or invoking a file that the repair touched — counts as *use*. A listing of
   `/app/skills/` in the NoSkill arm, or reading the file that contains the anchor, is not use.
   (v1 of the detector got this wrong: it scored 13 shipped-anchor "hits" for an agent that had
   merely read the skill, and mislabelled the case as `Recover`.)
2. **Paired attribution.** A response is attributed to the inconsistency only when the Fixed arm
   does not show it. `Bypass` in both arms is model habit; a related check that fails in **both**
   arms is not attributable to the inconsistency at all.
3. **Response and outcome are separate fields** (as are score and cost); no single label mixes them.

## Step-1 deliverables (done)

**49 descriptors.** Each records the repaired files, the exact removed/added lines, the taxonomy
class, plus two anchor sets and the verifier checks tied to them:

| signal | coverage | example (`playwright-ci-inprogress-report`) |
|---|---|---|
| shipped-only anchors (code-like tokens) | 34/49 tasks have ≥1; 19 have ≥5 | `FAILED_RUNS`, `No failed workflows.` |
| fixed-only anchors | 42/49 | `REPORT_RUNS`, `No failed or in-progress workflows.` |
| related verifier checks | 46/49 | `check_report_notes_inprogress_workflows` … |

Anchor extraction keeps only code-like tokens (backticked spans, flags, quoted literals, snake_case,
dotted names, hyphenated compounds, numbers, paths) because prose words cannot be matched against a
trajectory. Verifier check names are matched on the canonical suffix (`check_foo` ↔ `::test_foo`);
without that normalisation v1 matched nothing.

**Detector v2** labels each paired case: `exposed`, `response` ∈ {Follow→failure, Recover→success
with overhead, Bypass (induced), Bypass (both arms), Used→both arms fail, Not used, unchanged},
plus the per-arm signature (skill reads, anchors used, errors after first use, failed checks, cost).

**Batch labels** (`analysis/labels.csv`, 450 paired cells on the current manifest):

| response | n | attributable to the inconsistency? |
|---|---|---|
| Recover → success with overhead | 181 | yes |
| Used → both arms fail the same checks | 104 | **no** (control category) |
| Follow → failure | 84 | yes |
| Not used (no exposure) | 29 | — |
| Bypass (both arms) | 26 | no (model habit) |
| Bypass (induced) | 14 | yes |
| Used, outcome unchanged | 12 | — |

Exposure is high and similar across models (haiku 120/156, qwen 122/147, deepseek 139/147), but the
*response* is not: episodes that follow the inconsistency into failure number **35 (qwen), 31
(haiku), 18 (deepseek)** — the same ordering as the RQ2 effectiveness gaps. DeepSeek is exposed most
often yet fails least often, i.e. the difference between models lies in what they do after contact
with the inconsistency, not in whether they make contact.

## Known gaps before these numbers can enter the paper

1. **Validation.** The detectors are rule-based and unvalidated. Hand-label 30–40 cells (stratified
   by type and response) and report agreement; treat the machine labels as candidates until then.
2. **`Recover` must require a measured overhead.** v2 fires on *use + an error or a fixed-anchor
   action*; it should additionally require Δtokens or Δwall-clock > 0 against the paired Fixed cell,
   otherwise "with overhead" is asserted rather than shown.
3. **Check-level semantics.** For `Used → both arms fail`, the failing check must be excluded from
   that task's attributable set (it is a property of the task, not of the inconsistency).
4. **Trial policy.** `labels.csv` uses every manifest cell, which includes stale task-package
   versions and the six-trial batch-12 tasks (450 rather than 441 pairs). Regenerate on the final,
   version-consistent RQ2 selection before reporting.
5. **Bypass detection** currently keys on skill reads only; add a check that no alternative access
   path (`.claude/skills` vs `/app/skills`) was used.

## Next steps

1. Regenerate labels on the final selection; add the Δcost requirement for `Recover`.
2. Hand-validation sample → agreement table.
3. Produce the four tables: type × exposure, type × response (with the habit/induced split),
   response × outcome (score vs Δcost), and the mechanism matrix.
4. Select 3–5 cases per dominant mechanism for the qualitative section, with decisive turns and
   numbers rather than narrative.
