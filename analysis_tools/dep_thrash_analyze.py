#!/usr/bin/env python3
"""Count what the repair actually targets: dependency-plumbing work in the traces.

`total_tokens` is confounded -- it rises both when a cell thrashes and when a cell
finally gets far enough into the task to do real work (see analysis/r1-causal-evidence.md,
grid-dispatch-operator). This measures the quantity R1/R2/R3 act on directly:

  * dependency-related Bash commands (pip / install / venv / apt / conda)
  * failed shells matching an environment signature
  * which skills were loaded (a doc repair can only work if the doc is read)

Usage:
  python3 analysis_tools/dep_thrash_analyze.py \
      --study drs=experiments/drs-v2-20260925 \
      --study prior=haiku45-threeway-20260917
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

DEP_RE = re.compile(r'\b(pip3?|uv)\s+(install|pip)|python3?\s+-m\s+venv|apt(-get)?\s+install|conda\s+install')
SIGS = [
    ('externally-managed', re.compile(r'externally-managed-environment')),
    ('no_module', re.compile(r"No module named '([^']+)'")),
    ('cmd_not_found', re.compile(r'(\S+): command not found')),
]


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def scan(log: Path):
    dep = total = 0
    sig = Counter()
    skills = []
    with log.open(errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get('type') == 'assistant':
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_use':
                        continue
                    if c.get('name') == 'Skill':
                        skills.append((c.get('input') or {}).get('skill'))
                    elif c.get('name') == 'Bash':
                        total += 1
                        if DEP_RE.search(str((c.get('input') or {}).get('command') or '')):
                            dep += 1
            elif o.get('type') == 'user':
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_result':
                        continue
                    txt = text_of(c.get('content'))
                    for name, rx in SIGS:
                        m = rx.search(txt)
                        if m:
                            sig[name] += 1
    return dep, total, sig, skills


def find_trace(cell_dir: Path):
    hits = sorted(cell_dir.rglob('cli.stdout.jsonl'))
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--study', action='append', required=True,
                    help='label=path, repeatable')
    args = ap.parse_args()

    per = defaultdict(lambda: defaultdict(list))
    for spec in args.study:
        label, _, path = spec.partition('=')
        runs = Path(path) / 'runs'
        for cell in sorted(p for p in runs.iterdir() if p.is_dir()):
            rid = cell.name
            arm = rid.split('__')[1] if rid.count('__') >= 2 else '?'
            tr = find_trace(cell)
            if not tr:
                continue
            dep, total, sig, skills = scan(tr)
            per[label][arm].append(dict(cell=rid, dep=dep, total=total,
                                        sig=dict(sig), skills=skills))

    for label, arms in per.items():
        print(f'\n######## study={label}')
        print(f"{'arm':16}{'n':>4}{'dep_cmds(med)':>15}{'dep/total':>11}"
              f"{'ext-mgd':>9}{'no_mod':>8}{'cmdNF':>7}{'skills/run':>11}")
        print('-' * 82)
        for arm, rows in sorted(arms.items()):
            dep = [r['dep'] for r in rows]
            tot = [r['total'] for r in rows]
            sig = Counter()
            for r in rows:
                sig.update(r['sig'])
            sk = [len(r['skills']) for r in rows]
            print(f'{arm:16}{len(rows):>4}{statistics.median(dep):>15.0f}'
                  f'{sum(dep)/max(sum(tot),1):>11.2%}'
                  f'{sig["externally-managed"]:>9}{sig["no_module"]:>8}'
                  f'{sig["cmd_not_found"]:>7}{statistics.mean(sk):>11.1f}')

    print('\n=== per-cell dependency commands ===')
    for label, arms in per.items():
        for arm, rows in sorted(arms.items()):
            for r in sorted(rows, key=lambda x: x['cell']):
                print(f"  {label:8}{r['cell']:46} dep={r['dep']:>2} "
                      f"bash={r['total']:>2} skills={len(r['skills'])}")


if __name__ == '__main__':
    main()
