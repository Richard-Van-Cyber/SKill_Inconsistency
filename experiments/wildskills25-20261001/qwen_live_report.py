#!/usr/bin/env python3
"""Live effectiveness/efficiency report for a running wildskills study.

Reads the study's cell result.json files (canonical cells only) and prints/writes:
  * per-arm mean score (scored-only and ITT), n, truncation rate
  * per-arm median calls / turns / tokens / agent seconds (untruncated cells only)
  * paired Δ(FixedSkill − OriginalSkill) as tasks accumulate

Usage: qwen_live_report.py <study_dir> [--csv progress.csv] [--md LIVE.md]
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import statistics
import sys
import datetime

STUDY = sys.argv[1]
CSV = sys.argv[sys.argv.index('--csv') + 1] if '--csv' in sys.argv else None
MD = sys.argv[sys.argv.index('--md') + 1] if '--md' in sys.argv else None
CANON = re.compile(r'^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$')
ARMS = ['NoSkill', 'OriginalSkill', 'FixedSkill']


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def fs(v, nd=3):
    return '—' if v is None else f'{v:.{nd}f}'


def fk(v):
    return '—' if v is None else f'{v/1000:.0f}k'


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


cells = []
for p in glob.glob(os.path.join(STUDY, 'runs', '*', '*', 'result.json')):
    cell = p.split('/runs/')[1].split('/')[0]
    if not CANON.match(cell):
        continue
    try:
        d = json.load(open(p))
    except Exception:
        continue
    cells.append(dict(task=cell.split('__')[0], arm=cell.split('__')[1],
                      status=d.get('status'), score=d.get('score'),
                      truncated=(d.get('budget_stop_reason') or '') == 'api_budget'
                      or str(d.get('termination_reason')) == 'api_budget',
                      calls=d.get('api_calls'), turns=d.get('num_turns'),
                      tokens=d.get('total_tokens'), secs=d.get('agent_seconds'),
                      reason=d.get('termination_reason')))

now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
lines = [f'# qwen3.6:35b on wildskills25 — live report  ({now})', '',
         f'cells started **{len(cells)}** / 207   '
         f'graded **{sum(1 for c in cells if c["status"] == "graded")}**   '
         f'other {sum(1 for c in cells if c["status"] != "graded")}', '',
         '| arm | mean(scored) | n | mean(ITT) | n | trunc | calls | turns | tokens | agent s |',
         '|---|---|---|---|---|---|---|---|---|---|']
row = {'at': now, 'cells': len(cells)}
for arm in ARMS:
    a = [c for c in cells if c['arm'] == arm]
    if not a:
        continue
    sc = [c for c in a if c['status'] == 'graded' and c['score'] is not None]
    u = [c for c in sc if not c['truncated']]
    tr = 100 * sum(1 for c in a if c['truncated']) / len(a)
    m_sc, m_itt = mean([c['score'] for c in sc]), mean([(c['score'] or 0) for c in a])
    lines.append(f'| {arm} | {fs(m_sc)} | {len(sc)} | {fs(m_itt)} | {len(a)} | {tr:.0f}% | '
                 f'{fs(med([c["calls"] for c in u]), 0)} | {fs(med([c["turns"] for c in u]), 0)} | '
                 f'{fk(med([c["tokens"] for c in u]))} | {fs(med([c["secs"] for c in u]), 0)} |')
    row[f'{arm}_scored'], row[f'{arm}_itt'], row[f'{arm}_n'], row[f'{arm}_trunc'] = \
        (round(m_sc, 4) if m_sc is not None else ''), (round(m_itt, 4) if m_itt is not None else ''), \
        len(a), round(tr, 1)

by = {}
for c in cells:
    if c['score'] is not None:
        by.setdefault(c['task'], {}).setdefault(c['arm'], []).append(c['score'])
ds = {t: mean(v['FixedSkill']) - mean(v['OriginalSkill'])
      for t, v in by.items() if v.get('FixedSkill') and v.get('OriginalSkill')}
if ds:
    vals = list(ds.values())
    lines += ['', f'**paired Δ(F−O)**: tasks={len(ds)}  improved={sum(1 for v in vals if v > 1e-9)} '
                  f'tied={sum(1 for v in vals if abs(v) <= 1e-9)} worse={sum(1 for v in vals if v < -1e-9)}  '
                  f'mean={mean(vals):+.3f}  median={med(vals):+.3f}']
    top = sorted(ds.items(), key=lambda kv: -kv[1])[:4]
    lines.append('top: ' + ', '.join(f'{t} {v:+.3f}' for t, v in top))
    row['paired_tasks'] = len(ds)
    row['paired_mean'] = round(mean(vals), 4)

text = '\n'.join(lines)
print(text)
if MD:
    open(MD, 'w').write(text + '\n')
if CSV:
    new = not os.path.exists(CSV)
    with open(CSV, 'a', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=sorted(row))
        if new:
            w.writeheader()
        w.writerow(row)
