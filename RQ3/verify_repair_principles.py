#!/usr/bin/env python3
"""Audit all 49 fixed_skills overlays against the repair principles (minimality / no leakage / no
stray files / direction). Reads the descriptors already built by build_descriptors.py."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPO = Path('.')
DESC = REPO / 'RQ3' / 'descriptors'
TASKS = REPO / 'wildskills' / 'dynamic_eval' / 'tasks'
FIXED = REPO / 'wildskills' / 'dynamic_eval' / 'fixed_skills'

LEAK = re.compile(r'/app/workspace|/logs/verifier|/verifier/|ORACLE_|expected_ids|verify_[a-z]|'
                  r'ctrf|reward\.(txt|json)|solve\.sh|__pycache__')

def tree(root: Path) -> dict:
    if not root.is_dir():
        return {}
    return {str(p.relative_to(root)): p for p in root.rglob('*') if p.is_file()}

rows = []
for t in sorted(p.name for p in TASKS.iterdir() if p.is_dir()):
    d = json.load(open(DESC / f'{t}.json'))
    src = tree(TASKS / t / 'environment' / 'skills')
    dst = tree(FIXED / t / 'environment' / 'skills')
    changed = d.get('changed_files', [])
    added_lines, removed_lines = [], []
    for f, v in d.get('diff', {}).items():
        added_lines += v.get('added', [])
        removed_lines += v.get('removed', [])
    new_files = sorted(set(dst) - set(src))
    deleted_files = sorted(set(src) - set(dst))
    # scope of leakage: what the repair *introduced* (added lines + brand-new files)
    leak_hits = []
    for ln in added_lines:
        if LEAK.search(ln):
            leak_hits.append(ln.strip()[:80])
    for nf in new_files:
        try:
            txt = (dst[nf]).read_text(errors='ignore')
        except Exception:
            continue
        for m in LEAK.finditer(txt):
            leak_hits.append(f'{nf}: {m.group(0)}')
    # direction: which file types changed
    kinds = {('doc' if f.endswith('.md') else 'code') for f in changed}
    direction = 'code' if kinds == {'code'} else ('doc' if kinds == {'doc'} else 'both')
    # stray files inside the overlay (pyc, etc.)
    stray = [f for f in dst if '__pycache__' in f or f.endswith(('.pyc', '.DS_Store'))]
    rows.append(dict(task=t, batch=d.get('batch'), changed=len(changed), plus=len(added_lines),
                     minus=len(removed_lines), new_files=len(new_files), deleted=len(deleted_files),
                     direction=direction, leak=len(leak_hits), stray=len(stray),
                     leak_eg=leak_hits[:2]))

import collections
print('=== 全部 49 个 fixed overlay 复核')
print(f'{"task":<40}{"batch":<9}{"chg":>4}{"+/-":>10}{"new":>4}{"del":>4}{"dir":<6}{"leak":>5}{"stray":>6}')
for r in rows:
    print(f'{r["task"]:<40}{r["batch"]:<9}{r["changed"]:>4}{str(r["plus"])+"/"+str(r["minus"]):>10}'
          f'{r["new_files"]:>4}{r["deleted"]:>4}{r["direction"]:<6}{r["leak"]:>5}{r["stray"]:>6}')
print()
print('=== 汇总')
print('  有 leak 命中的 task:', sum(1 for r in rows if r['leak']), '/', len(rows))
print('  有 stray 文件的 task:', sum(1 for r in rows if r['stray']))
print('  新增文件的 task:', sum(1 for r in rows if r['new_files']), '（新增文件合法仅当补齐文档承诺）')
print('  方向分布:', dict(collections.Counter(r['direction'] for r in rows)))
for r in rows:
    if r['leak']:
        print(f'   leak [{r["task"]}]:', r['leak_eg'])
