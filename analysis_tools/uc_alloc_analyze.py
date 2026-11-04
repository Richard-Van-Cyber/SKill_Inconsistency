#!/usr/bin/env python3
"""Analyse the UC alloc-semantics paired runs.

The skill's SKILL.md hands the agent a copy-paste `alloc` helper whose body never
reads lb / ub / integer, while the call sites beside it ask for
`lb=0, ub=1, integer=True`. The verifier asserts commitment is binary. So the
decisive evidence is at the artifact level: does report.json contain commitment
values other than 0/1?

Usage: python3 analysis_tools/uc_alloc_analyze.py
"""
from __future__ import annotations

import json
import os
import re
import statistics
import tarfile
from collections import defaultdict

STUDY = 'experiments/uc-alloc-adv-20260924'
RUNS = os.path.join(STUDY, 'runs')

# the helper body as shipped, and the repaired body
DOC_ALLOC = re.compile(r'offset\[name\]\s*=\s*idx\s*\n\s*n\s*\+=\s*size\s*\n\s*return idx')
FIXED_ALLOC = re.compile(r'bounds\[int\(j\)\]|integrality\[int\(j\)\]')


def find_main(cell_dir):
    for root, dirs, _f in os.walk(cell_dir):
        if os.path.basename(root).endswith('__claude-haiku') and 'api' in dirs:
            return root
    return None


def read_report(cell_dir):
    for root, _dirs, files in os.walk(cell_dir):
        for f in files:
            if f == 'agent-artifacts.tgz':
                try:
                    with tarfile.open(os.path.join(root, f)) as t:
                        for m in t.getmembers():
                            if m.name.endswith('report.json'):
                                return json.load(t.extractfile(m))
                except Exception:
                    return None
    return None


def commitment_stats(rep):
    """(n_total, n_offending) over every thermal generator's commitment array."""
    if not rep:
        return 0, 0
    tot = bad = 0
    for g in rep.get('thermal_generators') or []:
        for v in g.get('commitment') or []:
            try:
                f = float(v)
            except (TypeError, ValueError):
                bad += 1; tot += 1; continue
            tot += 1
            if abs(f - round(f)) > 1e-6 or round(f) not in (0, 1):
                bad += 1
    return tot, bad


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
        rep = read_report(d)
        tot, bad = commitment_stats(rep)
        main_dir = find_main(d)
        copied_doc = copied_fixed = False
        if main_dir:
            blob = []
            for line in open(os.path.join(main_dir, 'cli.stdout.jsonl'), errors='replace'):
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get('type') == 'assistant':
                    for c in (o.get('message') or {}).get('content') or []:
                        if isinstance(c, dict) and c.get('type') == 'tool_use':
                            blob.append(json.dumps(c.get('input') or {}, ensure_ascii=False))
            b = "\n".join(blob)
            copied_doc = bool(DOC_ALLOC.search(b)) or 'def alloc(' in b
            copied_fixed = bool(FIXED_ALLOC.search(b))
        rows.append(dict(
            cell=cell, condition=r.get('condition'), status=r.get('status'),
            score=r.get('score'), api_calls=r.get('api_calls'),
            total_tokens=r.get('total_tokens'), agent_seconds=r.get('agent_seconds'),
            has_report=rep is not None,
            commit_total=tot, commit_bad=bad,
            commit_binary_ok=(tot > 0 and bad == 0),
            uses_alloc=copied_doc, uses_repaired_helper=copied_fixed,
            objective=((rep or {}).get('summary') or {}).get('objective_cost'),
        ))
    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':46}{'score':>6}{'report':>7}{'commit':>8}{'bad':>6}"
           f"{'binaryOK':>9}{'alloc':>7}{'fixed':>6}{'obj':>12}")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print(f"{r['cell'][:45]:46}{str(r['score']):>6}{str(r['has_report']):>7}"
              f"{r['commit_total']:>8}{r['commit_bad']:>6}{str(r['commit_binary_ok']):>9}"
              f"{str(r['uses_alloc']):>7}{str(r['uses_repaired_helper']):>6}"
              f"{(r['objective'] if r['objective'] is not None else float('nan')):12.1f}")
    print()
    g = defaultdict(list)
    for r in rows:
        g[r['condition']].append(r)
    print(f"{'condition':16}{'n':>3}{'mean score':>12}{'runs w/ report':>16}"
          f"{'runs non-binary':>17}{'runs using alloc':>18}{'med calls':>11}")
    for k in sorted(g):
        rs = g[k]
        sc = [x['score'] for x in rs if x['score'] is not None]
        calls = [x['api_calls'] for x in rs if x['api_calls'] is not None]
        print(f"{k:16}{len(rs):3}"
              f"{(statistics.mean(sc) if sc else float('nan')):12.3f}"
              f"{sum(1 for x in rs if x['has_report']):16}"
              f"{sum(1 for x in rs if x['has_report'] and not x['commit_binary_ok']):17}"
              f"{sum(1 for x in rs if x['uses_alloc']):18}"
              f"{(statistics.median(calls) if calls else 0):11.0f}")


if __name__ == '__main__':
    main()
