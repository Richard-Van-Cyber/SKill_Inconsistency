#!/usr/bin/env python3
"""Effectiveness + efficiency report for the v2 repair study, and the head-to-head
comparison against the 2026-09-17 arms.

    python3 analysis_tools/drs_v2_analyze.py [<study-dir>] [--out <md>]

Definitions are copied from haiku45-threeway-20260917/analysis/matched-budget-report.md
so the two reports can be read side by side:
  * effectiveness  = mean `score` over graded cells; a truncated cell still counts
                     (its score is real, just budget-limited) and is marked `T`
  * efficiency     = api_calls / agent_seconds / total_tokens, and -- because a
                     truncated cell's token count is an artefact of the cap -- the
                     headline efficiency aggregate uses UNTRUNCATED cells only.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

DEFAULT_STUDY = Path('experiments/drs-v2-20260925')
PRIOR_STUDY = Path('haiku45-threeway-20260917')
TASKS = ['civ6-adjacency-optimizer', 'court-form-filling',
         'crystallographic-wyckoff-position-analysis', 'data-to-d3', 'dialogue-parser',
         'energy-market-pricing', 'fix-druid-loophole-cve', 'fix-erlang-ssh-cve',
         'grid-dispatch-operator', 'mario-coin-counting']
# court-form-filling's test.sh only reads pytest's exit code, and its checkbox tests
# SKIP (not fail) when the produced PDF has no form fields -> reward 1 means "no test
# ran". Reported both with and without it, as the prior report does.
VERIFIER_DEFECT = {'court-form-filling'}


def truncated(r):
    """A cell is budget-limited when the harness says so.

    In this study family `result.json` carries the reason in `budget_stop_reason` /
    `raw_termination_reason` (value `api_budget`; 24 of 90 cells in the 2026-09-17 study).
    There is no `api_budget` object, so testing only for one silently marks every cell
    untruncated and corrupts the efficiency aggregate.
    """
    if r.get('budget_stop_reason') == 'api_budget':
        return True
    if r.get('raw_termination_reason') == 'api_budget':
        return True
    b = r.get('api_budget') or {}
    return bool(b.get('exhausted') or b.get('truncated') or r.get('truncated'))


def load(runs_dir: Path, arms):
    """-> {arm: {task: {rep: row}}}"""
    out = {a: defaultdict(dict) for a in arms}
    for p in sorted(runs_dir.glob('*/result.json')):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        lid = r.get('logical_run_id') or p.parent.name
        arm = r.get('arm')
        if arm not in out:
            # prior study has no `arm` field: recover it from the run id
            for a in arms:
                if f'__{a}__' in lid:
                    arm = a
                    break
            else:
                continue
        parts = lid.split('__')
        if len(parts) < 3:
            continue
        task, rep = parts[0], parts[-1]
        out[arm][task][rep] = r
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def fmt(x, nd=3):
    return '-' if x is None else f'{x:.{nd}f}'


def cell(r):
    if not r:
        return '-'
    s = fmt(r.get('score'))
    return s + ('T' if truncated(r) else '')


def eff(r):
    if not r:
        return '-'
    c, sec, tk = r.get('api_calls'), r.get('agent_seconds'), r.get('total_tokens')
    s = f'{c if c is not None else "-"}/{sec if sec is not None else "-"}s/' \
        f'{(tk/1000):.0f}k' if tk else f'{c if c is not None else "-"}/{sec if sec is not None else "-"}s/-'
    return s + ('*' if truncated(r) else '')


def aggregate(data, arms, tasks):
    """Mean score (effectiveness) and untruncated-only medians (efficiency)."""
    rows = {}
    for a in arms:
        scores, calls, secs, toks = [], [], [], []
        n = 0
        for t in tasks:
            for rep, r in data[a].get(t, {}).items():
                if not r.get('finished_at'):
                    continue
                n += 1
                if r.get('score') is not None:
                    scores.append(r['score'])
                if not truncated(r):
                    if r.get('api_calls') is not None:
                        calls.append(r['api_calls'])
                    if r.get('agent_seconds') is not None:
                        secs.append(r['agent_seconds'])
                    if r.get('total_tokens') is not None:
                        toks.append(r['total_tokens'])
        rows[a] = dict(n=n, eff_mean=mean(scores), eff_n=len(scores),
                       calls=statistics.median(calls) if calls else None,
                       secs=statistics.median(secs) if secs else None,
                       tok=statistics.median(toks) if toks else None,
                       tok_sum=sum(toks) if toks else None, eff_eff_n=len(toks))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('study', nargs='?', default=str(DEFAULT_STUDY))
    ap.add_argument('--out', default=None)
    ap.add_argument('--prior', default=str(PRIOR_STUDY))
    ap.add_argument('--arms', default='NoSkill,OriginalSkill,RepairV2',
                    help='comma-separated arm names as they appear in logical_run_id')
    ap.add_argument('--baseline-from', default=str(PRIOR_STUDY),
                    help='study to take any arm not present in <study> from. NoSkill and '
                         'OriginalSkill already exist there under an identical config '
                         '(same runner, budget, tasks), so only RepairV2 is re-run.')
    args = ap.parse_args()
    study = Path(args.study)
    v2_arms = [a.strip() for a in args.arms.split(',') if a.strip()]
    data = load(study / 'runs', v2_arms)

    # Fill in arms this study did not run from the frozen baseline study.
    base_study = Path(args.baseline_from)
    borrowed = []
    if base_study.exists() and base_study.resolve() != study.resolve():
        base = load(base_study / 'runs', v2_arms)
        for a in v2_arms:
            if not data[a] and base[a]:
                data[a] = base[a]
                borrowed.append(a)
    if borrowed:
        print(f'[baseline] took {borrowed} from {base_study}')

    L = []
    A = L.append
    A('# DRS 修复 v2（trace-driven, doc-only）三臂结果\n')
    A(f'RepairV2 来自 `{study}`；'
      + (f'{"、".join(borrowed)} 来自 `{base_study}`（同配置基线）' if borrowed else '')
      + '  \n')
    A('预算 60 req / 1,000,000 tok / 32,768 out；runner 源码两处逐字节相同，'
      '任务包逐字节相同，只有 skill 内容不同。\n')
    A('标记：`T` = 被 api_budget 截断；`*` = 该 cell 被截断，效率数值不可比。'
      'Efficiency 汇总**只用未截断 cell**。\n')

    A('\n## 1. Effectiveness（三臂 × 10 task）\n')
    A('| task | ' + ' | '.join(v2_arms) + ' |')
    A('|---|' + '---|' * len(v2_arms))
    for t in TASKS:
        A(f'| {t} | ' + ' | '.join(fmt(mean([r.get("score") for r in data[a].get(t, {}).values()]))
                                   for a in v2_arms) + ' |')
    A('\n## 2. 汇总\n')
    ag = aggregate(data, v2_arms, TASKS)
    agx = aggregate(data, v2_arms, [t for t in TASKS if t not in VERIFIER_DEFECT])
    base, treat = v2_arms[0], v2_arms[-1]
    A(f'| 口径 | ' + ' | '.join(v2_arms) + f' | {treat} − {base} | '
      f'{treat} − {v2_arms[-2] if len(v2_arms) > 2 else base} |')
    A('|---|---|---|---|---|')
    for name, g in (('全部 10 task', ag), ('剔除 court（verifier 缺陷）', agx)):
        cells = ' | '.join(fmt(g[a]['eff_mean']) + f" (n={g[a]['eff_n']})" for a in v2_arms)
        if None in (g[treat]['eff_mean'], g[base]['eff_mean']):
            A(f'| {name} | {cells} | - | - |')
            continue
        d1 = g[treat]['eff_mean'] - g[base]['eff_mean']
        mid = v2_arms[-2] if len(v2_arms) > 2 else base
        d2 = g[treat]['eff_mean'] - g[mid]['eff_mean']
        A(f'| {name} | {cells} | {d1:+.3f} | {d2:+.3f} |')

    A('\n## 3. Efficiency（未截断 cell 的中位数）\n')
    A('| 口径 | arm | n | calls | agent_seconds | tokens(median) | tokens(sum) |')
    A('|---|---|---|---|---|---|---|')
    for name, g in (('全部 10 task', ag), ('剔除 court', agx)):
        for a in v2_arms:
            r = g[a]
            A(f'| {name} | {a} | {r["eff_eff_n"]} | {r["calls"]} | {r["secs"]} | '
              f'{(r["tok"]/1000):.0f}k | {(r["tok_sum"]/1000):.0f}k |' if r['tok'] else
              f'| {name} | {a} | 0 | - | - | - | - |')

    A('\n## 4. 逐 task 效率（calls/seconds/tokens）\n')
    A('| task | rep | ' + ' | '.join(v2_arms) + ' |')
    A('|---|' + '---|' * (len(v2_arms) + 1))
    for t in TASKS:
        reps = sorted({r for a in v2_arms for r in data[a].get(t, {})})
        for rep in reps:
            A(f'| {t} | {rep} | ' + ' | '.join(eff(data[a].get(t, {}).get(rep)) for a in v2_arms) + ' |')

    A('\n## 5. 被截断的 cell\n')
    trunc = []
    for a in v2_arms:
        for t in TASKS:
            for rep, r in sorted(data[a].get(t, {}).items()):
                if truncated(r):
                    trunc.append(f'{a}/{t}/{rep}')
    A(', '.join(trunc) if trunc else '（无）')

    text = '\n'.join(L) + '\n'
    out = Path(args.out) if args.out else study / 'analysis' / 'matched-budget-report.md'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    print(f'\n[written] {out}')


if __name__ == '__main__':
    main()
