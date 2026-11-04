#!/usr/bin/env python3
"""Mechanism + G4 (load-bearing) analysis over the wildskills13 runs.

For every cell it derives, from the run directory:
  * score / status / truncation / token & turn cost
  * the **defect surface** — the files the FixedSkill overlay changes relative to the pristine
    skill tree (so "did the agent engage with the defect?" has a mechanical definition)
  * whether the agent *read or wrote* any defect-surface file (from the trajectory's tool calls)
  * whether it delivered the task's artifact, and the error signatures it hit
    (command not found / ModuleNotFoundError / externally-managed / traceback / ENOENT)

Outputs `experiments/wildskills13-dataset/mechanism.csv` + a console digest.

Usage: python3 analyze_mechanism.py [--studies s1,s2] [--out ../../experiments/wildskills13-dataset]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXPERIMENTS = REPO / 'experiments'
TASKS = REPO / 'wildskills' / 'dynamic_eval' / 'tasks'
FIXED = REPO / 'wildskills' / 'dynamic_eval' / 'fixed_skills'

ERROR_PATTERNS = {
    'command_not_found': re.compile(r'command not found'),
    'module_missing': re.compile(r'ModuleNotFoundError|No module named'),
    'externally_managed': re.compile(r'externally-managed-environment'),
    'no_such_file': re.compile(r'No such file or directory|ENOENT'),
    'traceback': re.compile(r'Traceback \(most recent call last\)'),
    'permission': re.compile(r'Permission denied'),
    'timeout': re.compile(r'timed out|Timeout'),
}


def defect_surface(task: str) -> list[str]:
    """Files the repaired overlay changes = the defect surface (relative to the skill tree)."""
    pristine = TASKS / task / 'environment' / 'skills'
    overlay = FIXED / task / 'environment' / 'skills'
    if not pristine.is_dir() or not overlay.is_dir():
        return []
    changed, added = [], []
    for f in overlay.rglob('*'):
        if not f.is_file() or '__pycache__' in str(f):
            continue
        rel = f.relative_to(overlay)
        counterpart = pristine / rel
        if not counterpart.is_file():
            added.append(str(rel))
        elif counterpart.read_bytes() != f.read_bytes():
            changed.append(str(rel))
    return changed + added


def trajectory_events(path: Path):
    with path.open(errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:  # noqa: BLE001
                continue


def analyse_cell(cell_dir: Path, surface: list[str]) -> dict:
    out = {'cell': cell_dir.name}
    res = cell_dir / 'result.json'
    payload = {}
    # the driver writes result.json next to the run dir the agent wrote into
    for cand in (res, *cell_dir.glob('*/result.json')):
        if cand.is_file():
            payload = json.loads(cand.read_text())
            break
    out.update({'status': payload.get('status'), 'score': payload.get('score'),
                'tokens': payload.get('total_tokens'), 'turns': payload.get('num_turns'),
                'calls': payload.get('api_calls'),
                'truncated': (payload.get('budget_stop_reason') or '') == 'api_budget'})

    traj = next(iter(cell_dir.glob('*/cli.stdout.jsonl')), None)
    reads = writes = bash = 0
    touched: set[str] = set()
    errors: Counter = Counter()
    if traj:
        for ev in trajectory_events(traj):
            msg = ev.get('message') or {}
            for block in (msg.get('content') or []):
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'tool_use':
                    name = block.get('name')
                    inp = block.get('input') or {}
                    text = json.dumps(inp, ensure_ascii=False)
                    if name == 'Bash':
                        bash += 1
                    elif name == 'Read':
                        reads += 1
                    elif name in ('Write', 'Edit', 'NotebookEdit'):
                        writes += 1
                    for rel in surface:
                        base = Path(rel).name
                        if rel in text or (len(base) > 6 and base in text):
                            touched.add(rel)
                elif block.get('type') == 'tool_result':
                    content = block.get('content')
                    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                    # A *missing* resource cannot be opened, so the agent meets it as an ENOENT /
                    # directory listing in a tool RESULT. Count those path mentions too, otherwise
                    # external_resource_invalid tasks look like "never engaged" by construction.
                    for rel in surface:
                        base = Path(rel).name
                        if rel in (text or '') or (len(base) > 6 and base in (text or '')):
                            touched.add(rel)
                    for key, rx in ERROR_PATTERNS.items():
                        if rx.search(text or ''):
                            errors[key] += 1
    out.update({'bash_calls': bash, 'reads': reads, 'writes': writes,
                'surface_files': ';'.join(surface),
                'surface_touched': ';'.join(sorted(touched)),
                'touched_any': bool(touched),
                'errors': ';'.join(f'{k}={v}' for k, v in errors.most_common())})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--studies', default='wildskills13-20260929,wildskills13b-20260929,'
                                        'wildskills13c-20260929')
    ap.add_argument('--out', default=str(EXPERIMENTS / 'wildskills13-dataset'))
    args = ap.parse_args()
    studies = [s for s in args.studies.split(',') if s]

    rows = []
    for study in studies:
        runs = EXPERIMENTS / study / 'runs'
        if not runs.is_dir():
            print(f'  [warn] {study}: no runs/ (not synced yet)', file=sys.stderr)
            continue
        for cell in sorted(p for p in runs.iterdir() if p.is_dir()):
            task, _, rest = cell.name.partition('__')
            arm = rest.split('__')[0] if rest else ''
            r = analyse_cell(cell, defect_surface(task))
            r['study'] = study
            r['task'] = task
            r['arm'] = arm
            rows.append(r)
    if not rows:
        print('nothing to analyse')
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'mechanism.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f'wrote {out}/mechanism.csv ({len(rows)} cells)\n')
    print(f"{'task':<24} {'arm':<14} {'score':>6} {'turns':>5} {'bash':>5} {'touch':>5}  errors")
    for r in sorted(rows, key=lambda r: (r['task'], r['arm'], r['cell'])):
        sc = r['score'] if r['score'] is not None else '—'
        print(f"{r['task'][:23]:<24} {r['arm']:<14} {str(sc):>6} {str(r['turns'] or '—'):>5} "
              f"{r['bash_calls']:>5} {'yes' if r['touched_any'] else 'no':>5}  {r['errors'][:40]}")

    print('\n— load-bearing summary: OriginalSkill cells that touched the defect surface —')
    by_task = defaultdict(lambda: [0, 0])
    for r in rows:
        if r['arm'] == 'OriginalSkill':
            by_task[r['task']][1] += 1
            by_task[r['task']][0] += bool(r['touched_any'])
    for task, (hit, n) in sorted(by_task.items()):
        print(f'  {task:<24} {hit}/{n} cells engaged with the defective file')
    return 0


if __name__ == '__main__':
    sys.exit(main())
