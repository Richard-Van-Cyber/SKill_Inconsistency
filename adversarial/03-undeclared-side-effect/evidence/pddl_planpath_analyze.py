#!/usr/bin/env python3
"""Analyse the pddl plan-path adversarial paired runs.

The skill's `save-plan` writes the text plan, then reopens
`path.replace('.txt', '.pkl')` in binary mode. When `path` has no `.txt`, that
expression equals `path`, so the text plan is overwritten by a pickle. The
task's shipped problem.json uses `.txt` (bug dormant); the adversarial variant
uses `.plan` (bug live).

Decisive evidence is therefore at the artifact level: is each plan file text or
pickle bytes? The verifier's own docstring notes "no reference pickle is
required", so a pickle there is an undeclared side effect, not an input.

Usage: python3 analysis_tools/pddl_planpath_analyze.py
"""
from __future__ import annotations

import json
import os
import statistics
import tarfile
from collections import defaultdict

STUDY = 'experiments/pddl-planpath-adv-20260924'
RUNS = os.path.join(STUDY, 'runs')


def plan_files(cell_dir):
    """Return {basename: 'text'|'pickle'|'missing'} for task*.txt / task*.plan."""
    found = {}
    for root, _dirs, files in os.walk(cell_dir):
        for f in files:
            if f == 'agent-artifacts.tgz':
                try:
                    with tarfile.open(os.path.join(root, f)) as t:
                        for m in t.getmembers():
                            base = os.path.basename(m.name)
                            if base.startswith('task') and (base.endswith('.txt') or base.endswith('.plan')):
                                data = t.extractfile(m).read(32)
                                if data.startswith(b'\x80\x04') or data.startswith(b'\x80\x05'):
                                    found[base] = 'pickle'
                                elif data.strip():
                                    found[base] = 'text'
                except Exception as exc:
                    found['<err>'] = str(exc)[:60]
    return found


def main():
    if not os.path.isdir(RUNS):
        raise SystemExit(f'no runs at {RUNS}')
    rows = []
    for cell in sorted(os.listdir(RUNS)):
        d = os.path.join(RUNS, cell)
        rp = os.path.join(d, 'result.json')
        if not os.path.isdir(d) or not os.path.exists(rp):
            continue
        r = json.load(open(rp))
        pf = plan_files(d)
        task = r.get('task', '')
        rows.append(dict(
            cell=cell, task=task, condition=r.get('condition'),
            variant='plan' if task.endswith('-plan') else 'txt',
            status=r.get('status'), score=r.get('score'),
            api_calls=r.get('api_calls'), total_tokens=r.get('total_tokens'),
            plans=pf,
            n_pickle=sum(1 for v in pf.values() if v == 'pickle'),
            n_text=sum(1 for v in pf.values() if v == 'text'),
        ))
    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':46}{'variant':8}{'cond':16}{'score':>6}{'calls':>6}"
           f"{'text':>6}{'pickle':>8}  plans")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print(f"{r['cell'][:45]:46}{r['variant']:8}{r['condition']:16}"
              f"{str(r['score']):>6}{str(r['api_calls']):>6}"
              f"{r['n_text']:6}{r['n_pickle']:8}  {r['plans']}")
    print()
    g = defaultdict(list)
    for r in rows:
        g[(r['variant'], r['condition'])].append(r)
    print(f"{'variant':8}{'condition':16}{'n':>3}{'mean score':>12}"
          f"{'runs w/ pickle':>16}{'med calls':>11}{'med tok k':>11}")
    for k in sorted(g):
        rs = g[k]
        sc = [x['score'] for x in rs if x['score'] is not None]
        calls = [x['api_calls'] for x in rs if x['api_calls'] is not None]
        toks = [x['total_tokens'] for x in rs if x['total_tokens'] is not None]
        print(f"{k[0]:8}{k[1]:16}{len(rs):3}"
              f"{(statistics.mean(sc) if sc else float('nan')):12.3f}"
              f"{sum(1 for x in rs if x['n_pickle']):16}"
              f"{(statistics.median(calls) if calls else 0):11.0f}"
              f"{(statistics.median(toks)/1000 if toks else 0):11.0f}")


if __name__ == '__main__':
    main()
