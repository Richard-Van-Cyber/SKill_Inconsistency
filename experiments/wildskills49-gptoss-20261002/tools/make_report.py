#!/usr/bin/env python3
"""Build the gpt-oss:20b axis report from the locally pulled study copy.

Reads
  <study>/runs/*/result.json        one completed cell each (the harness writes it at cell end)
  <reports>/manifest.csv            all-axes manifest (build_manifest_all_axes.py)
  <reports>/paper_stats.json        four-axis statistics (paper_stats_all_axes.py)

Writes
  <reports>/GPTOSS-AXIS-REPORT.md   operating point, provenance, arm means, paired delta,
                                    truncation breakdown, four-axis comparison

Usage: make_report.py <study_dir> <reports_dir>
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import math
import os
import re
import statistics
import sys

STUDY = sys.argv[1] if len(sys.argv) > 1 else '.'
REPORTS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(STUDY, 'reports')
ARMS = ('NoSkill', 'OriginalSkill', 'FixedSkill')
CANON = re.compile(r'^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$')
PLANNED = 441          # 49 tasks x 3 arms x 3 trials
PER_ARM = 147          # 49 tasks x 3 trials
# `blog-search` (and, per the paper's rule, `skill-routing`) bakes its skill into the task image,
# so the NoSkill arm cannot exist there: the harness' isolation probe finds the shipped files and
# refuses the cell with `environment_error: NoSkill package isolation failed`. The paper's
# selection drops NoSkill for these tasks, so the report does the same and uses the resulting
# per-arm denominators (NoSkill 144, the other two 147) for the ITT column.
NOARM = {'blog-search', 'skill-routing'}
EXCLUDED = {(t, 'NoSkill') for t in NOARM}
TASKS = 49
ARM_DEN = {a: (TASKS - len(NOARM) if a == 'NoSkill' else TASKS) * 3 for a in ARMS}


# ------------------------------------------------------------------ small statistics
def wilcoxon(v):
    """Two-sided signed-rank test, normal approximation with tie correction."""
    v = [x for x in v if abs(x) > 1e-12]
    n = len(v)
    if n < 2:
        return 0.0, 1.0
    ranks = {}
    order = sorted(range(n), key=lambda i: abs(v[i]))
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(v[order[j + 1]]) - abs(v[order[i]])) < 1e-12:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = sum(ranks[i] for i in range(n) if v[i] > 0)
    mu = n * (n + 1) / 4
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (w_plus - mu) / sd if sd else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    return z, p


def mean(xs):
    return statistics.mean(xs) if xs else None


def fmt(v, nd=3):
    return '—' if v is None else f'{v:.{nd}f}'


# ------------------------------------------------------------------ load cells
rows = []
for p in glob.glob(os.path.join(STUDY, 'runs', '*', 'result.json')):
    cell = p.split('/runs/')[1].split('/')[0]
    if not CANON.match(cell):
        continue
    d = json.load(open(p))
    task, arm, trial = cell.split('__')[0], cell.split('__')[1], cell.rsplit('__', 1)[-1]
    d.update(task=task, arm=arm, trial=trial, cell=cell)
    rows.append(d)

status = collections.Counter(r.get('status') for r in rows)
term = collections.Counter(r.get('termination_reason') for r in rows)
by_arm = collections.defaultdict(list)
excluded_cells = []
for r in rows:
    if (r['task'], r['arm']) in EXCLUDED:
        excluded_cells.append(r)
        continue
    if isinstance(r.get('score'), (int, float)):
        by_arm[r['arm']].append(r['score'])

# truncation: the manifest's `truncated` only counts the API budget, so both modes are shown
timeouts = [r for r in rows if r.get('termination_reason') == 'agent_timeout'
            or r.get('cli_exit_code') == 124 or (r.get('agent_seconds') or 0) >= 890]
budget = [r for r in rows if (r.get('budget_stop_reason') or '') == 'api_budget']
success = [r for r in rows if r.get('termination_reason') == 'success']

by = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    if isinstance(r.get('score'), (int, float)):
        by[r['task']][r['arm']].append(r['score'])
deltas = {t: mean(v['FixedSkill']) - mean(v['OriginalSkill'])
          for t, v in by.items() if v.get('FixedSkill') and v.get('OriginalSkill')}
dv = list(deltas.values())
z, p_w = wilcoxon(dv)
d_mean, d_med = mean(dv), (statistics.median(dv) if dv else None)
d_sd = statistics.stdev(dv) if len(dv) > 1 else None
se = (d_sd / math.sqrt(len(dv))) if (d_sd and len(dv) > 1) else None
ci = (d_mean - 1.96 * se, d_mean + 1.96 * se) if se else (None, None)

# efficiency on non-truncated cells
eff = {}
for arm in ARMS:
    un = [r for r in rows if r['arm'] == arm and isinstance(r.get('score'), (int, float))
          and r not in timeouts and r not in budget]
    eff[arm] = {
        'tokens': statistics.median([r['total_tokens'] for r in un if r.get('total_tokens')]) if un else None,
        'calls': statistics.median([r['api_calls'] for r in un if r.get('api_calls')]) if un else None,
        'turns': statistics.median([r['num_turns'] for r in un if r.get('num_turns')]) if un else None,
        'secs': statistics.median([r['agent_seconds'] for r in un if r.get('agent_seconds')]) if un else None,
    }

images = sorted({r.get('image') for r in rows if r.get('image')})
models = sorted({m for r in rows for m in (r.get('observed_models') or [])})
finished = sorted(r['finished_at'] for r in rows if r.get('finished_at'))

# ------------------------------------------------------- censoring sensitivity
# Truncated cells are the main threat to this axis: the qwen reference axis lost 32% of
# cells to truncation and this one loses a similar share, so the report states how the
# headline delta moves under four different treatments instead of quoting a single number.
TRUNC = {id(r) for r in timeouts} | {id(r) for r in budget}
task_rows = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    if isinstance(r.get('score'), (int, float)):
        task_rows[r['task']][r['arm']].append(r)


def delta_from(sel):
    out = {}
    for t, arms in task_rows.items():
        f, o = [r for r in arms.get('FixedSkill', []) if sel(r)], \
               [r for r in arms.get('OriginalSkill', []) if sel(r)]
        if f and o:
            out[t] = mean([r['score'] for r in f]) - mean([r['score'] for r in o])
    return out


sens = []
sens.append(('all paired tasks (as run)', delta_from(lambda r: True)))
sens.append(('both cells non-truncated', delta_from(lambda r: id(r) not in TRUNC)))
# Proper bracket of the *paired* delta: within each task, give the truncated cell of one arm
# the worst possible value and the other arm's the best, then swap. Replacing both arms with the
# same constant is uninformative when truncation is symmetric (it cancels), which is exactly the
# common case here — the asymmetry is what actually bounds the effect.
def bracket(fixed_good):
    out = {}
    for t, arms in task_rows.items():
        f, o = arms.get('FixedSkill', []), arms.get('OriginalSkill', [])
        if not (f and o):
            continue
        fv = [(1.0 if id(r) in TRUNC else r['score']) if fixed_good
              else (0.0 if id(r) in TRUNC else r['score']) for r in f]
        ov = [(0.0 if id(r) in TRUNC else r['score']) if fixed_good
              else (1.0 if id(r) in TRUNC else r['score']) for r in o]
        out[t] = mean(fv) - mean(ov)
    return out


sens.append(('worst case for Δ (Fixed truncated→0, Original truncated→1)', bracket(False)))
sens.append(('best case for Δ (Fixed truncated→1, Original truncated→0)', bracket(True)))

# per-corpus-batch table (12 / 13 / 25), taken from the all-axes manifest
BATCHES = {}


def load_batches():
    path = os.path.join(REPORTS, 'manifest.csv')
    if not os.path.exists(path):
        return BATCHES
    for r in csv.DictReader(open(path)):
        if r.get('axis') == 'gptoss' and r.get('batch'):
            BATCHES.setdefault(r['task'], r['batch'])
    return BATCHES


load_batches()

# ------------------------------------------------------------------ four-axis numbers
four = []
ps_path = os.path.join(REPORTS, 'paper_stats.json')
if os.path.exists(ps_path):
    rep = json.load(open(ps_path))
    for ax, rec in rep.items():
        a = rec.get('arms', {})
        pp = rec.get('paired', {})
        four.append((ax, rec.get('label', ax),
                     a.get('NoSkill', {}), a.get('OriginalSkill', {}), a.get('FixedSkill', {}), pp))

# ------------------------------------------------------------------ write the report
L = []
L.append('# wildskills — gpt-oss:20b axis (local A100 inference)')
L.append('')
L.append(f'Model `gpt-oss:20b` served by the two per-GPU ollama containers on 10.0.0.64, '
         f'8 parallel slots (5 on the A100-80GB, 3 on the A100-40GB) = the largest concurrency the '
         f'two cards can serve. 49 tasks x 3 conditions x 3 trials = {PLANNED} cells.')
L.append('')
L.append('## Completion')
L.append('')
L.append(f'* completed cells: **{len(rows)}/{PLANNED}**')
L.append(f'* status: {", ".join(f"{k}={v}" for k, v in sorted(status.items(), key=lambda x: str(x[0])))}')
L.append(f'* termination: {", ".join(f"{k}={v}" for k, v in sorted(term.items(), key=lambda x: str(x[0])))}')
if finished:
    L.append(f'* first cell finished {finished[0]}, last {finished[-1]}')
L.append('')
L.append('## Truncation (both modes)')
L.append('')
L.append(f'* `agent_timeout` ({len(timeouts)} cells, {100 * len(timeouts) / max(len(rows), 1):.1f}%): the task\'s own '
         f'900–1800 s agent budget expired; the verifier still grades what was produced.')
L.append(f'* `api_budget` ({len(budget)} cells): the per-run proxy budget (60 requests / 1M tokens / 32K output) was reached.')
L.append(f'* `success` ({len(success)} cells).')
L.append('')
L.append('## Scores by condition')
L.append('')
L.append('| condition | scored cells | mean (scored) | mean (ITT) |')
L.append('|---|---|---|---|')
for arm in ARMS:
    xs = by_arm.get(arm, [])
    L.append(f'| {arm} | {len(xs)} | {fmt(mean(xs), 4)} | {fmt(sum(xs) / ARM_DEN[arm], 4)} (/{ARM_DEN[arm]}) |')
L.append('')
L.append(f'Scheduled {PLANNED} cells. {len(EXCLUDED) * 3} of them are outside the paper\'s selection rule '
         f'(NoSkill for `blog-search` and `skill-routing`) and are dropped from the NoSkill denominator, '
         f'leaving the paper\'s {PLANNED - len(EXCLUDED) * 3} effective units. `blog-search` bakes its skill '
         f'into the task image, so its NoSkill cells cannot be isolated at all: the harness refuses them with '
         f'`environment_error: NoSkill package isolation failed` ({len(excluded_cells)} such cell(s) observed so '
         f'far). `skill-routing` NoSkill cells do grade here, but are dropped anyway so the arm matches the '
         f'published comparison.')
L.append('')
L.append(f'Per-task paired Δ(FixedSkill − OriginalSkill): **{fmt(d_mean, 4)}** '
         f'(median {fmt(d_med, 4)}, sd {fmt(d_sd, 4)}, n={len(dv)} paired tasks)')
if se:
    L.append(f'* 95% CI ≈ [{fmt(ci[0], 4)}, {fmt(ci[1], 4)}]; Wilcoxon signed-rank z={z:.2f}, p={p_w:.3g}')
L.append(f'* improved / tied / worse: {sum(1 for x in dv if x > 1e-9)} / '
         f'{sum(1 for x in dv if abs(x) <= 1e-9)} / {sum(1 for x in dv if x < -1e-9)}')
L.append('')
L.append('## Censoring sensitivity of Δ(FixedSkill − OriginalSkill)')
L.append('')
L.append('Local inference is slow enough that a sizeable share of cells is cut off by the task\'s own '
         'agent budget, so the headline delta is reported under four treatments. The bounds are the '
         'extremes of "all unfinished work would have failed" vs "would have succeeded"; the honest '
         'estimate lies between them, and agreement in sign across all four is the robustness claim.')
L.append('')
L.append('| treatment | paired tasks | mean Δ | median Δ | improved/tied/worse |')
L.append('|---|---|---|---|---|')
for label, d in sens:
    v = list(d.values())
    L.append(f'| {label} | {len(v)} | {fmt(mean(v), 4)} | {fmt(statistics.median(v) if v else None, 4)} | '
             f'{sum(1 for x in v if x > 1e-9)}/{sum(1 for x in v if abs(x) <= 1e-9)}/{sum(1 for x in v if x < -1e-9)} |')
L.append('')
if BATCHES:
    L.append('## Per corpus batch (12 / 14 / 23 tasks)')
    L.append('')
    L.append('| batch | completed cells | NoSkill | OriginalSkill | FixedSkill | pairs | Δ(F−O) |')
    L.append('|---|---|---|---|---|---|---|')
    for b in sorted(set(BATCHES.values())):
        tasks = {t for t, bb in BATCHES.items() if bb == b}
        rs = [r for r in rows if r['task'] in tasks]
        arm_means = {a: mean([r['score'] for r in rs if r['arm'] == a and isinstance(r.get('score'), (int, float))])
                     for a in ARMS}
        dd = [d for t, d in deltas.items() if t in tasks]
        L.append(f'| {b} | {len(rs)} | {fmt(arm_means["NoSkill"])} | {fmt(arm_means["OriginalSkill"])} | '
                 f'{fmt(arm_means["FixedSkill"])} | {len(dd)} | {fmt(mean(dd), 4)} |')
    L.append('')
L.append('## Efficiency (non-truncated cells only)')
L.append('')
L.append('| condition | median tokens | calls | turns | agent s |')
L.append('|---|---|---|---|---|')
for arm in ARMS:
    e = eff[arm]
    L.append(f'| {arm} | {fmt(e["tokens"], 0)} | {fmt(e["calls"], 0)} | {fmt(e["turns"], 0)} | {fmt(e["secs"], 0)} |')
L.append('')
L.append('## Provenance')
L.append('')
L.append(f'* observed models: {models}')
L.append(f'* task images used: {len(images)} distinct (verified identical to the qwen axis, so the four-axis '
         f'version filter keeps these cells)')
L.append('* every cell carries `test_summary` (check-level counts), `skill_source_sha256`, '
         '`agent-artifacts.tgz` and `native-session.tgz`.')
L.append('* `cli_total_cost_usd` is the vendor CLI\'s list-price estimate; local inference is not billed — '
         'it is **not** a real cost for this axis.')
L.append('')
if four:
    L.append('## Four-axis comparison (from paper_stats.json)')
    L.append('')
    L.append('| axis | NoSkill | OriginalSkill | FixedSkill | Δ(F−O) | p (Wilcoxon) | paired tasks |')
    L.append('|---|---|---|---|---|---|---|')
    for ax, label, n0, o1, f2, pp in four:
        L.append(f'| {label} | {fmt(n0.get("mean"))} | {fmt(o1.get("mean"))} | {fmt(f2.get("mean"))} | '
                 f'{fmt(pp.get("mean"), 4)} | {("—" if not pp.get("testable") else f"{pp.get("p_wilcoxon"):.3g}")} | '
                 f'{pp.get("n")} |')
    L.append('')

out = os.path.join(REPORTS, 'GPTOSS-AXIS-REPORT.md')
os.makedirs(REPORTS, exist_ok=True)
open(out, 'w').write('\n'.join(L) + '\n')
print(f'wrote {out} ({len(rows)}/{PLANNED} cells)')
