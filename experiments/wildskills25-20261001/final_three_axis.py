#!/usr/bin/env python3
"""Final three-axis statistics on a strictly comparable basis.

Selection rule (one observation per experimental unit):
  * trial ∈ {r1, r2, r3}
  * exclude the placebo and pilot studies (they are extra conditions, not the 3-arm design)
  * blog-search / skill-routing have no NoSkill arm (matching the design used on all axes)
  * keep only cells whose task-package image equals the task's CURRENT version (taken from the qwen
    axis, which was run last and whose images were verified against a fresh build).  Among cells that
    pass, keep the one from the latest study.  This removes the version drift found in the older
    haiku / deepseek batch12 studies.

Usage: final_three_axis.py <manifest.csv>
"""
from __future__ import annotations

import collections
import csv
import re
import statistics
import sys

rows = list(csv.DictReader(open(sys.argv[1])))
AXES = ('haiku', 'deepseek', 'qwen')
ARMS = ('NoSkill', 'OriginalSkill', 'FixedSkill')
NOARM = {'blog-search', 'skill-routing'}


def num(v):
    return float(v) if v not in ('', None, 'None') else None


def m(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def is_aux(r):
    return 'placebo' in r['batch'] or 'pilot' in r['batch']


def study_date(s):
    mm = re.search(r'(\d{8})', s)
    return mm.group(1) if mm else '0'


# current task-package version per task, derived from the qwen axis (run last, images verified)
cur = {}
for r in rows:
    if r['axis'] == 'qwen' and r['image'] and not is_aux(r):
        cur.setdefault(r['task'], set()).add(r['image'])
cur = {t: sorted(v)[0] for t, v in cur.items()}

print('=== 三轴终版（严格同口径：当前任务包版本 + r1–r3 + 单元去重）')
print(f'{"axis":<10}{"arm":<16}{"mean":>8}{"n":>5}{"calls":>7}{"turns":>7}{"tokens":>8}{"agent s":>9}{"trunc":>7}')
summary = {}
for ax in AXES:
    a = [r for r in rows if r['axis'] == ax and not is_aux(r)]
    best = {}
    dropped = 0
    for r in a:
        if r['trial'] not in ('r1', 'r2', 'r3'):
            continue
        k = (r['task'], r['arm'], r['trial'])
        if k[0] in NOARM and k[1] == 'NoSkill':
            continue
        cim = cur.get(k[0])
        if cim and r['image'] != cim:
            dropped += 1
            continue
        prev = best.get(k)
        if prev is None or study_date(r['study']) > study_date(prev['study']):
            best[k] = r
    cells = list(best.values())
    for arm in ARMS:
        s = [r for r in cells if r['arm'] == arm]
        if not s:
            continue
        sc = [r for r in s if r['status'] == 'graded' and num(r['score']) is not None]
        u = [r for r in sc if r['truncated'] != 'True']
        tr = 100 * sum(1 for r in s if r['truncated'] == 'True') / len(s)
        print(f'{ax:<10}{arm:<16}{m([num(r["score"]) for r in sc]):>8.3f}{len(sc):>5}'
              f'{med([num(r["api_calls"]) for r in u]) or 0:>7.0f}'
              f'{med([num(r["num_turns"]) for r in u]) or 0:>7.0f}'
              f'{(med([num(r["total_tokens"]) for r in u]) or 0) / 1000:>7.0f}k'
              f'{med([num(r["agent_seconds"]) for r in u]) or 0:>9.0f}{tr:>6.0f}%')
    by = collections.defaultdict(dict)
    for r in cells:
        if num(r['score']) is not None:
            by[r['task']].setdefault(r['arm'], []).append(num(r['score']))
    ds = {t: m(v['FixedSkill']) - m(v['OriginalSkill'])
          for t, v in by.items() if v.get('FixedSkill') and v.get('OriginalSkill')}
    v = list(ds.values())
    n = len(v)
    t = m(v) / (statistics.pstdev(v) / n ** 0.5)
    print(f'  -> units={len(cells)} paired={n} (丢弃旧版本格 {dropped})  '
          f'improved={sum(1 for x in v if x > 1e-9)} tied={sum(1 for x in v if abs(x) <= 1e-9)} '
          f'worse={sum(1 for x in v if x < -1e-9)}  mean Δ={m(v):+.3f} median={med(v):+.3f} '
          f'sd={statistics.pstdev(v):.3f}  t={t:.2f}')
    summary[ax] = (len(cells), n,
                   m([num(r['score']) for r in cells if r['arm'] == 'NoSkill' and r['status'] == 'graded']),
                   m([num(r['score']) for r in cells if r['arm'] == 'OriginalSkill' and r['status'] == 'graded']),
                   m([num(r['score']) for r in cells if r['arm'] == 'FixedSkill' and r['status'] == 'graded']),
                   m(v), t)
    print()

print('=== 汇总')
print(f'{"axis":<10}{"units":>6}{"pairs":>7}{"NoSkill":>9}{"Original":>10}{"Fixed":>8}{"Δ":>8}{"t":>7}')
for ax, (u, n, a1, b1, c1, d1, t) in summary.items():
    print(f'{ax:<10}{u:>6}{n:>7}{a1:>9.3f}{b1:>10.3f}{c1:>8.3f}{d1:>+8.3f}{t:>7.2f}')
