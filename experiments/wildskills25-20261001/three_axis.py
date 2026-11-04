#!/usr/bin/env python3
"""Three-axis (or single-axis) comparison on one batch, read from the collection manifest.

Usage: three_axis.py <manifest.csv> [batch] [axis1,axis2,...]
"""
from __future__ import annotations

import collections
import csv
import statistics
import sys

PATH = sys.argv[1]
BATCH = sys.argv[2] if len(sys.argv) > 2 else 'wildskills25'
AXES = (sys.argv[3].split(',') if len(sys.argv) > 3 else ['haiku', 'deepseek', 'qwen'])
ARMS = ['NoSkill', 'OriginalSkill', 'FixedSkill']


def num(v):
    return float(v) if v not in ('', None, 'None') else None


def m(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


rows = [r for r in csv.DictReader(open(PATH)) if r['batch'] == BATCH and r['axis'] in AXES]
print(f'batch={BATCH}  axes={AXES}  cells={len(rows)}')
hdr = (f'{"axis":<10}{"arm":<15}{"scored":>8}{"n":>4}{"ITT":>8}'
       f'{"calls":>7}{"turns":>7}{"tokens":>8}{"agent s":>9}{"trunc":>7}')
print(hdr)
for ax in AXES:
    for arm in ARMS:
        a = [r for r in rows if r['axis'] == ax and r['arm'] == arm]
        if not a:
            continue
        sc = [r for r in a if r['status'] == 'graded' and num(r['score']) is not None]
        s = [num(r['score']) for r in sc]
        itt = [num(r['score']) or 0.0 for r in a]
        u = [r for r in sc if r['truncated'] != 'True']
        tk, ag = med([num(r['total_tokens']) for r in u]), med([num(r['agent_seconds']) for r in u])
        cl, tu = med([num(r['api_calls']) for r in u]), med([num(r['num_turns']) for r in u])
        tr = 100 * sum(1 for r in a if r['truncated'] == 'True') / len(a)
        print(f'{ax:<10}{arm:<15}{m(s):>8.3f}{len(sc):>4}{m(itt):>8.3f}'
              f'{cl or 0:>7.0f}{tu or 0:>7.0f}{(tk or 0)/1000:>7.0f}k{ag or 0:>9.0f}{tr:>6.0f}%')
    print()

print('per-task paired Δ(F−O):')
for ax in AXES:
    by = collections.defaultdict(dict)
    for r in rows:
        if r['axis'] == ax and num(r['score']) is not None:
            by[r['task']].setdefault(r['arm'], []).append(num(r['score']))
    ds = {t: m(v['FixedSkill']) - m(v['OriginalSkill'])
          for t, v in by.items() if v.get('FixedSkill') and v.get('OriginalSkill')}
    v = list(ds.values())
    if not v:
        continue
    imp = sum(1 for x in v if x > 1e-9)
    tie = sum(1 for x in v if abs(x) <= 1e-9)
    wor = sum(1 for x in v if x < -1e-9)
    print(f'  {ax:<10} tasks={len(ds):<3} improved={imp:<3} tied={tie:<3} worse={wor:<3} '
          f'mean Δ={m(v):+.3f}  median Δ={med(v):+.3f}  sd={statistics.pstdev(v):.3f}')
    top = sorted(ds.items(), key=lambda kv: -kv[1])[:4]
    bot = sorted(ds.items(), key=lambda kv: kv[1])[:3]
    print('     best : ' + ', '.join(f'{t} {x:+.3f}' for t, x in top))
    print('     worst: ' + ', '.join(f'{t} {x:+.3f}' for t, x in bot))
