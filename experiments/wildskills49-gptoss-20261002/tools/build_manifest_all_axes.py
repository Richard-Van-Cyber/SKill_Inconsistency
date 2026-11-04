#!/usr/bin/env python3
"""Build the wildskills collection manifest: one row per cell, both model axes.

Axes / batches (a batch = a group of tasks built together):
  haiku   : wildskills12 (the original 12), wildskills13 (14), wildskills25 (23)
  deepseek: wildskills12 (12, done), wildskills13 (14), wildskills25 (23, running)

Writes <out>/manifest.csv, <out>/SUMMARY.md and copies the analysis-relevant files list.
Usage: python3 build_manifest.py [experiments_dir] [out_dir]
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import re
import sys

EXP = sys.argv[1] if len(sys.argv) > 1 else '/home/user/project/experiments'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(EXP, 'wildskills-collection')
CANON = re.compile(r'^.+__(NoSkill|OriginalSkill|FixedSkill|RepairedSkill)__r[0-9]+$')

# study -> (axis, batch)
STUDIES = {
    # haiku — original 12-task batch (built incrementally)
    'wildskills-20260926': ('haiku', 'wildskills12'), 'wildskills2-20260926': ('haiku', 'wildskills12'),
    'wildskills3-20260926': ('haiku', 'wildskills12'), 'wildskills3b-20260926': ('haiku', 'wildskills12'),
    'wildskills3c-20260926': ('haiku', 'wildskills12'), 'wildskills5-20260927': ('haiku', 'wildskills12'),
    'wildskills5b-20260927': ('haiku', 'wildskills12'), 'wildskills6-20260927': ('haiku', 'wildskills12'),
    'wildskills7-20260927': ('haiku', 'wildskills12'), 'wildskills8-20260927': ('haiku', 'wildskills12'),
    'wildskills9-20260927': ('haiku', 'wildskills12'), 'wildskills10-20260927': ('haiku', 'wildskills12'),
    # haiku — batch 13
    'wildskills13-20260929': ('haiku', 'wildskills13'), 'wildskills13b-20260929': ('haiku', 'wildskills13'),
    'wildskills13c-20260929': ('haiku', 'wildskills13'), 'wildskills13-pilot-20260929': ('haiku', 'wildskills13-pilot'),
    'wildskills13-placebo-20260929': ('haiku', 'wildskills13-placebo'),
    # haiku — batch 25
    'wildskills25-20261001a': ('haiku', 'wildskills25'), 'wildskills25-20261001b': ('haiku', 'wildskills25'),
    'wildskills25-20261001c': ('haiku', 'wildskills25'),
    'wildskills25-placebo-20261001': ('haiku', 'wildskills25-placebo'),
    # deepseek
    'wildskills-deepseek-20260927': ('deepseek', 'wildskills12'),
    'wildskills-deepseek-b2-20260927': ('deepseek', 'wildskills12'),
    'wildskills13-deepseek-20260929': ('deepseek', 'wildskills13'),
    'wildskills25-deepseek-20261001': ('deepseek', 'wildskills25'),
    # local GPU ollama (A100) — qwen3.6:35b
    'wildskills25-ollama-20260930': ('qwen', 'wildskills25'),
    'wildskills12-ollama-20260930': ('qwen', 'wildskills12'),
    'wildskills12b-ollama-20260930': ('qwen', 'wildskills12'),
    'wildskills13-ollama-20260930': ('qwen', 'wildskills13'),
    # version-realignment runs (2026-10-01): re-ran cells whose task package version differed
    'wildskills12-realign-20261001': ('haiku', 'wildskills12'),
    'wildskills12b-realign-20261001': ('haiku', 'wildskills12'),
    'wildskills-realign-haiku-20261001': ('haiku', 'wildskills12'),
    'wildskills-realign-deepseek-20261001': ('deepseek', 'wildskills12'),
    'wildskills-gapfix-haiku-20261001': ('haiku', 'gapfix'),
    # local GPU ollama (A100) — gpt-oss:20b, all 49 tasks in one study. Its batch is
    # derived per task (TASK_BATCH below) so it lines up with the 12/14/23 batches of
    # the haiku/deepseek/qwen axes instead of appearing as one 49-task block.
    'wildskills49-gptoss-20261002': ('gptoss', 'wildskills49'),
}
EXTRA_NOTE = {'skillbench-deepseek-20260927': 'skillbench-25 corpus (not wildskills) — listed for completeness'}

# task -> corpus batch, taken from the batch studies' frozen WS_TASKS.txt
# (wildskills12 = 10 + wildskills12b = 2, wildskills13 = 14, wildskills25 = 23 => 49).
TASK_BATCH = {}


def _load_task_batches(exp):
    here = os.path.dirname(os.path.abspath(__file__))
    for study, batch in (('wildskills12-ollama-20260930', 'wildskills12'),
                         ('wildskills12b-ollama-20260930', 'wildskills12'),
                         ('wildskills13-ollama-20260930', 'wildskills13'),
                         ('wildskills25-ollama-20260930', 'wildskills25')):
        for cand in (os.path.join(exp, study, 'WS_TASKS.txt'),
                     os.path.join(here, 'WS_TASKS', study + '.txt')):
            if os.path.exists(cand):
                TASK_BATCH.update({t.strip(): batch for t in open(cand).read().split(',') if t.strip()})
                break
    return TASK_BATCH


FIELDS = ['axis', 'batch', 'study', 'task', 'arm', 'trial', 'model', 'status', 'score',
          'truncated', 'api_calls', 'num_turns', 'total_tokens', 'agent_seconds',
          'image', 'rel_path']


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    _load_task_batches(EXP)
    rows = []
    for study, (axis, batch) in STUDIES.items():
        for p in glob.glob(os.path.join(EXP, study, 'runs', '*', '*', 'result.json')):
            cell = p.split('/runs/')[1].split('/')[0]
            if not CANON.match(cell):
                continue
            try:
                r = json.load(open(p))
            except Exception:
                continue
            task, arm, trial = cell.split('__')[0], cell.split('__')[1], cell.rsplit('__', 1)[-1]
            if axis == 'gptoss':
                batch = TASK_BATCH.get(task, batch)
            rows.append({
                'axis': axis, 'batch': batch, 'study': study, 'task': task, 'arm': arm, 'trial': trial,
                'model': r.get('model') or (r.get('observed_models') or ['?'])[0],
                'status': r.get('status'), 'score': r.get('score'),
                'truncated': (r.get('budget_stop_reason') or '') == 'api_budget',
                'api_calls': r.get('api_calls'), 'num_turns': r.get('num_turns'),
                'total_tokens': r.get('total_tokens'), 'agent_seconds': r.get('agent_seconds'),
                'image': r.get('image'),
                'rel_path': os.path.relpath(os.path.dirname(p), EXP),
            })
    rows.sort(key=lambda r: (r['axis'], r['batch'], r['task'], r['arm'], r['trial']))
    with open(os.path.join(OUT, 'manifest.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    # summary
    L = ['# wildskills collection — index', '',
         f'{len(rows)} cells across {len({r["study"] for r in rows})} studies, '
         f'two model axes. Generated from `{EXP}`.', '',
         '| axis | batch | tasks | cells | graded | models |', '|---|---|---|---|---|---|']
    grp = collections.defaultdict(list)
    for r in rows:
        grp[(r['axis'], r['batch'])].append(r)
    for (axis, batch), rs in sorted(grp.items()):
        tasks = {r['task'] for r in rs}
        models = sorted({r['model'] for r in rs})
        graded = sum(1 for r in rs if r['status'] == 'graded')
        L.append(f'| {axis} | {batch} | {len(tasks)} | {len(rs)} | {graded} | {", ".join(models)} |')
    L += ['', '## per study', '', '| axis | study | cells | graded | tasks |', '|---|---|---|---|---|']
    st = collections.defaultdict(list)
    for r in rows:
        st[(r['axis'], r['study'])].append(r)
    for (axis, study), rs in sorted(st.items()):
        L.append(f'| {axis} | {study} | {len(rs)} | {sum(1 for r in rs if r["status"] == "graded")} '
                 f'| {len({r["task"] for r in rs})} |')
    if EXTRA_NOTE:
        L += ['', '## not part of the wildskills corpus', '']
        for k, v in EXTRA_NOTE.items():
            L.append(f'* `{k}` — {v}')
    open(os.path.join(OUT, 'SUMMARY.md'), 'w').write('\n'.join(L) + '\n')
    print(f'manifest.csv: {len(rows)} cells -> {OUT}')
    for (axis, batch), rs in sorted(grp.items()):
        print(f'  {axis:<9} {batch:<18} cells={len(rs):<4} graded={sum(1 for r in rs if r["status"]=="graded"):<4} '
              f'tasks={len({r["task"] for r in rs})}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
