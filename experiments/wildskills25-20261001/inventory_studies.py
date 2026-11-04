#!/usr/bin/env python3
"""Inventory every wildskills/skillbench study: cells, graded, and which model each cell used.

Usage: python3 inventory_studies.py [experiments_dir]
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

EXP = sys.argv[1] if len(sys.argv) > 1 else '/home/user/project/experiments'
CANON = re.compile(r'^.+__(NoSkill|OriginalSkill|FixedSkill|RepairedSkill)__r[0-9]+$')

rows = []
for d in sorted(glob.glob(os.path.join(EXP, '*'))):
    name = os.path.basename(d)
    if not (name.startswith('wildskills') or name.startswith('skillbench')):
        continue
    if not os.path.isdir(os.path.join(d, 'runs')):
        continue
    cells = graded = 0
    models = collections.Counter()
    tasks = set()
    arms = collections.Counter()
    for p in glob.glob(os.path.join(d, 'runs', '*', '*', 'result.json')):
        cell = p.split('/runs/')[1].split('/')[0]
        if not CANON.match(cell):
            continue
        try:
            r = json.load(open(p))
        except Exception:
            continue
        cells += 1
        m = r.get('model') or (r.get('observed_models') or ['?'])[0]
        models[str(m)] += 1
        tasks.add(cell.split('__')[0])
        arms[cell.split('__')[1]] += 1
        if r.get('status') == 'graded':
            graded += 1
    rows.append((name, cells, graded, len(tasks), dict(models), dict(arms)))

print(f'{"study":<42}{"cells":>6}{"graded":>7}{"tasks":>6}  models')
for n, c, g, t, m, a in rows:
    print(f'{n:<42}{c:>6}{g:>7}{t:>6}  {m}')

print()
print('== totals per model')
tot = collections.Counter()
for n, c, g, t, m, a in rows:
    for k, v in m.items():
        tot[k] += v
for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
    print(f'  {k:<28}{v:>6} cells')

print()
print('== wildskills studies by model')
for n, c, g, t, m, a in rows:
    if not n.startswith('wildskills'):
        continue
    primary = max(m, key=m.get) if m else '?'
    print(f'  {n:<42} {primary:<16} cells={c:<4} graded={g:<4} tasks={t}')
