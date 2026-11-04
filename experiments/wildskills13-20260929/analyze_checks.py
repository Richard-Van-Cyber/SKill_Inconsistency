#!/usr/bin/env python3
"""Per-check analysis for the wildskills13 runs ("open the reward").

Reward is passed/total and often saturates at 1.0; the CTRF report each verifier writes
(`benchflow/verifier/ctrf.json`) carries the individual check results, which is where the
signal actually lives. This script aggregates them:

  * per arm: check-level pass rate, alongside the reward mean
  * per task: Δ(Fixed − Original) on both reward and check pass rate
  * the **load-bearing checks**: checks whose pass rate differs between the arms — i.e. the
    ones the defect actually moves (batch 2 found reward-level Δ ≈ 0 while individual checks
    still separated)

Outputs experiments/wildskills13-dataset/checks.csv and prints a digest.

Usage: python3 analyze_checks.py [--studies ...] [--out ...]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXPERIMENTS = REPO / 'experiments'
ARMS = ['NoSkill', 'OriginalSkill', 'FixedSkill']


def cells(study: str):
    runs = EXPERIMENTS / study / 'runs'
    if not runs.is_dir():
        return
    for cell in sorted(p for p in runs.iterdir() if p.is_dir()):
        task, _, rest = cell.name.partition('__')
        arm = rest.split('__')[0] if rest else ''
        ctrf = next(iter(cell.glob('*/benchflow/verifier/ctrf.json')), None)
        if ctrf is None:
            continue
        try:
            data = json.loads(ctrf.read_text())
        except Exception:  # noqa: BLE001
            continue
        tests = (data.get('results') or {}).get('tests') or []
        res = next(iter(cell.glob('*/result.json')), None)
        payload = json.loads(res.read_text()) if res and res.is_file() else {}
        yield {'study': study, 'task': task, 'arm': arm, 'cell': cell.name,
               'score': payload.get('score'), 'status': payload.get('status'),
               'checks': [(t.get('name', '').replace('::test_', ''), t.get('status') == 'passed')
                          for t in tests]}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(v, nd=3):
    return '—' if v is None else f'{v:.{nd}f}'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--studies', default='wildskills13-20260929,wildskills13b-20260929,'
                                        'wildskills13c-20260929')
    ap.add_argument('--out', default=str(EXPERIMENTS / 'wildskills13-dataset'))
    args = ap.parse_args()
    studies = [s for s in args.studies.split(',') if s]

    rows, per_cell = [], []
    for study in studies:
        for c in cells(study) or []:
            per_cell.append(c)
            for name, ok in c['checks']:
                rows.append({'study': study, 'task': c['task'], 'arm': c['arm'],
                             'cell': c['cell'], 'check': name, 'passed': int(ok)})
    if not rows:
        print('no ctrf.json found — sync the runs first')
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'checks.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    L: list[str] = []
    A = L.append
    A('# wildskills13 — 逐检查项通过率（把 reward 打开）')
    A('')
    A(f'覆盖 {len(per_cell)} 个 cell、{len({r["check"] for r in rows})} 个不同检查项。')
    A('')
    A('| 臂 | cell | reward 均值 | 逐检查项通过率 |')
    A('|---|---|---|---|')
    for arm in ARMS:
        cs = [c for c in per_cell if c['arm'] == arm]
        if not cs:
            continue
        cr = [p for r in rows if r['arm'] == arm for p in [r['passed']]]
        A(f'| {arm} | {len(cs)} | {fmt(mean([c["score"] for c in cs]))} | '
          f'{fmt(mean(cr))} |')
    A('')

    # per-task deltas on reward and on check pass rate
    A('## 逐 task：reward Δ 与逐检查项 Δ（Fixed − Original）')
    A('')
    A('| task | reward O | reward F | Δreward | 检查项 O | 检查项 F | Δ检查项 |')
    A('|---|---|---|---|---|---|---|')
    by_task = defaultdict(dict)
    for c in per_cell:
        by_task[c['task']][c['arm']] = c
    for task in sorted(by_task):
        o, f = by_task[task].get('OriginalSkill'), by_task[task].get('FixedSkill')
        if not o or not f:
            continue
        ro = mean([c['score'] for c in per_cell if c['task'] == task and c['arm'] == 'OriginalSkill'])
        rf = mean([c['score'] for c in per_cell if c['task'] == task and c['arm'] == 'FixedSkill'])
        cro = mean([p for r in rows if r['task'] == task and r['arm'] == 'OriginalSkill'
                    for p in [r['passed']]])
        crf = mean([p for r in rows if r['task'] == task and r['arm'] == 'FixedSkill'
                    for p in [r['passed']]])
        A(f'| {task} | {fmt(ro)} | {fmt(rf)} | '
          f'{fmt(None if None in (ro, rf) else rf - ro)} | {fmt(cro)} | {fmt(crf)} | '
          f'{fmt(None if None in (cro, crf) else crf - cro)} |')
    A('')

    # load-bearing checks: pass rate differs between Original and Fixed by >= 0.25
    A('## 承重检查项（Fixed 与 Original 的通过率差 ≥ 0.25）')
    A('')
    A('| task | check | Original | Fixed | Δ |')
    A('|---|---|---|---|---|')
    n = 0
    for task in sorted(by_task):
        names = {r['check'] for r in rows if r['task'] == task}
        for name in sorted(names):
            po = mean([r['passed'] for r in rows
                       if r['task'] == task and r['arm'] == 'OriginalSkill' and r['check'] == name])
            pf = mean([r['passed'] for r in rows
                       if r['task'] == task and r['arm'] == 'FixedSkill' and r['check'] == name])
            if po is None or pf is None:
                continue
            if abs(pf - po) >= 0.25:
                A(f'| {task} | `{name}` | {fmt(po, 2)} | {fmt(pf, 2)} | {pf - po:+.2f} |')
                n += 1
    if not n:
        A('| — | （暂无：数据还不够或缺陷未承重） | | | |')
    A('')
    (out / 'checks.md').write_text('\n'.join(L) + '\n')
    print(f'wrote {out}/checks.csv ({len(rows)} check results) and {out}/checks.md')
    print('\n'.join(L[:14]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
