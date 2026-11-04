#!/usr/bin/env python3
"""Aggregate the whole collection manifest by model axis and batch.

Usage: python3 aggregate_axis.py [manifest.csv] [axis]
  axis defaults to 'haiku' (the other option is 'deepseek'; 'all' = both)

Prints, per batch and for the axis as a whole:
  * arm means, scored-only and ITT (unscored counted as 0)
  * per-task paired Δ(FixedSkill − OriginalSkill) summary + the extremes
  * efficiency: median calls / turns / tokens on untruncated cells, truncation rate
"""
from __future__ import annotations

import collections
import csv
import statistics
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else 'manifest.csv'
AXIS = sys.argv[2] if len(sys.argv) > 2 else 'haiku'
ARMS = ['NoSkill', 'OriginalSkill', 'FixedSkill', 'RepairedSkill']


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def f(v, nd=3):
    return '—' if v is None else f'{v:.{nd}f}'


def k(v):
    return '—' if v is None else f'{v / 1000:.0f}k'


rows = list(csv.DictReader(open(PATH)))
for r in rows:
    r['score'] = float(r['score']) if r['score'] not in ('', 'None') else None
    for fld in ('api_calls', 'num_turns', 'total_tokens', 'agent_seconds'):
        r[fld] = float(r[fld]) if r[fld] not in ('', 'None') else None
    r['truncated'] = str(r['truncated']).lower() == 'true'

sel = [r for r in rows if AXIS == 'all' or r['axis'] == AXIS]
print(f'axis={AXIS}  cells={len(sel)}  batches={sorted({r["batch"] for r in sel})}')

# normalise the repaired arm name across corpora
for r in sel:
    if r['arm'] == 'RepairedSkill':
        r['arm'] = 'FixedSkill'

for batch in sorted({r['batch'] for r in sel}):
    rs = [r for r in sel if r['batch'] == batch]
    tasks = sorted({r['task'] for r in rs})
    print(f'\n=== {batch}   {len(rs)} cells / {len(tasks)} tasks')
    print(f'{"arm":<15}{"mean(scored)":>13}{"n":>5}{"mean(ITT)":>11}{"n":>5}'
          f'{"calls":>7}{"turns":>7}{"tokens":>8}{"trunc":>7}')
    for arm in ARMS:
        a = [r for r in rs if r['arm'] == arm]
        if not a:
            continue
        sc = [r for r in a if r['status'] == 'graded' and r['score'] is not None]
        u = [r for r in sc if not r['truncated']]
        print(f'{arm:<15}{f(mean([r["score"] for r in sc])):>13}{len(sc):>5}'
              f'{f(mean([(r["score"] or 0) for r in a])):>11}{len(a):>5}'
              f'{f(med([r["api_calls"] for r in u]),1):>7}{f(med([r["num_turns"] for r in u]),1):>7}'
              f'{k(med([r["total_tokens"] for r in u])):>8}'
              f'{f(100*sum(1 for r in a if r["truncated"])/len(a),0):>6}%')
    # paired per-task deltas
    by = collections.defaultdict(dict)
    for r in rs:
        if r['score'] is not None:
            by[r['task']].setdefault(r['arm'], []).append(r['score'])
    ds = {t: mean(v['FixedSkill']) - mean(v['OriginalSkill'])
          for t, v in by.items() if v.get('FixedSkill') and v.get('OriginalSkill')}
    if ds:
        imp = sum(1 for v in ds.values() if v > 1e-9)
        tie = sum(1 for v in ds.values() if abs(v) <= 1e-9)
        wor = sum(1 for v in ds.values() if v < -1e-9)
        print(f'paired tasks={len(ds)}  improved={imp} tied={tie} worse={wor}  '
              f'mean Δ={f(mean(list(ds.values())))}  median Δ={f(med(list(ds.values())))}')
        top = sorted(ds.items(), key=lambda kv: -kv[1])[:5]
        bot = sorted(ds.items(), key=lambda kv: kv[1])[:4]
        print('  best : ' + '  '.join(f'{t}={v:+.3f}' for t, v in top))
        print('  worst: ' + '  '.join(f'{t}={v:+.3f}' for t, v in bot))

# ---- axis total, NOT split by batch (the headline view) --------------------------------
print(f'\n=== {AXIS.upper()} TOTAL — 不分批 ({len(sel)} cells, {len({r["task"] for r in sel})} distinct tasks)')
print(f'{"arm":<15}{"mean(scored)":>13}{"n":>5}{"mean(ITT)":>11}{"n":>5}'
      f'{"calls":>7}{"turns":>7}{"tokens":>8}{"agent s":>9}{"trunc":>7}')
for arm in ARMS:
    a = [r for r in sel if r['arm'] == arm]
    if not a:
        continue
    sc = [r for r in a if r['status'] == 'graded' and r['score'] is not None]
    u = [r for r in sc if not r['truncated']]
    print(f'{arm:<15}{f(mean([r["score"] for r in sc])):>13}{len(sc):>5}'
          f'{f(mean([(r["score"] or 0) for r in a])):>11}{len(a):>5}'
          f'{f(med([r["api_calls"] for r in u]),1):>7}{f(med([r["num_turns"] for r in u]),1):>7}'
          f'{k(med([r["total_tokens"] for r in u])):>8}{f(med([r["agent_seconds"] for r in u]),0):>9}'
          f'{f(100*sum(1 for r in a if r["truncated"])/len(a),0):>6}%')
# paired deltas across every task of the axis (trials averaged inside each arm)
by = collections.defaultdict(dict)
for r in sel:
    if r['score'] is not None:
        by[r['task']].setdefault(r['arm'], []).append(r['score'])
ds = {t: mean(v['FixedSkill']) - mean(v['OriginalSkill'])
      for t, v in by.items() if v.get('FixedSkill') and v.get('OriginalSkill')}
if ds:
    vals = list(ds.values())
    print(f'paired tasks={len(ds)}  improved={sum(1 for v in vals if v > 1e-9)} '
          f'tied={sum(1 for v in vals if abs(v) <= 1e-9)} worse={sum(1 for v in vals if v < -1e-9)}')
    print(f'  task-equal mean Δ(F−O)={f(mean(vals))}  median={f(med(vals))}  sd={f(statistics.pstdev(vals))}')
# cost per point
for arm in ARMS:
    a = [r for r in sel if r['arm'] == arm]
    tot_tok = sum(r['total_tokens'] or 0 for r in a)
    ssum = sum(r['score'] or 0 for r in a if r['status'] == 'graded')
    if a and ssum:
        print(f'  {arm:<15} 每 1 分的 token ≈ {tot_tok/ssum/1e6:.2f}M   (总 {tot_tok/1e6:.1f}M / 分数和 {ssum:.1f})')
