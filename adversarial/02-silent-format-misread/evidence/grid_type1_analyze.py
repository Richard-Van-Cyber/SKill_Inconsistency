#!/usr/bin/env python3
"""Analyse the grid Type-1 adversarial paired runs.

The instance is built so that the two readings of the data are 25x apart:

    verifier-objective optimum (MODEL ignored) :   200.00 $/h
    economically correct optimum (Type-1 read) : 5,000.00 $/h

so an agent's reported `cost_dollars_per_hour` classifies its behaviour directly.
The verifier accepts only 200 (tolerance -0.01%/+0.01%), so a Type-1-aware agent
is guaranteed to fail and a MODEL-ignoring agent is guaranteed to pass.

Usage: python3 analysis_tools/grid_type1_analyze.py
"""
from __future__ import annotations

import json
import os
import re
import statistics
from collections import defaultdict

STUDY = 'experiments/grid-type1-adv-20260924'
RUNS = os.path.join(STUDY, 'runs')

VERIFIER_OPT = 200.0     # what the grader expects
TRUE_OPT = 5000.0        # what the reference document's Type-1 advice yields

MARKERS = {
    'mentions_piecewise': re.compile(r'piecewise|piece-wise|breakpoint', re.I),
    'mentions_model_col': re.compile(r'gencost\s*\[\s*[^]]*,\s*0\s*\]|MODEL\s*==\s*1|model\s*column', re.I),
    'reads_col4to6':      re.compile(r'gencost\s*\[\s*[^]]*,\s*4\s*\]'),
}


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def scan(cell_dir):
    main = None
    for root, dirs, _f in os.walk(cell_dir):
        if os.path.basename(root).endswith('__claude-haiku') and 'api' in dirs:
            main = root
    if not main:
        return {}, 0, None
    marks = defaultdict(int)
    reported = None
    p = os.path.join(main, 'cli.stdout.jsonl')
    for line in open(p, errors='replace'):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get('type') != 'assistant':
            continue
        for c in (o.get('message') or {}).get('content') or []:
            if not isinstance(c, dict):
                continue
            if c.get('type') == 'tool_use':
                s = json.dumps(c.get('input') or {}, ensure_ascii=False)
                for k, rx in MARKERS.items():
                    marks[k] += len(rx.findall(s))
                # the agent's own report.json write reveals the reported cost
                if 'cost_dollars_per_hour' in s:
                    for m in re.finditer(r'cost_dollars_per_hour[^\d\-]{0,12}(-?\d+(?:\.\d+)?)', s):
                        reported = float(m.group(1))
    # also look at the archived artifact
    art = None
    for root, _d, files in os.walk(main):
        for f in files:
            if f == 'report.json':
                try:
                    art = json.load(open(os.path.join(root, f)))
                except Exception:
                    pass
    if art:
        v = (art.get('totals') or {}).get('cost_dollars_per_hour')
        if v is not None:
            reported = float(v)
    return dict(marks), 0, reported


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
        marks, _, reported = scan(d)
        task = r.get('task', '')
        if reported is None:
            reading = 'unknown'
        elif abs(reported - VERIFIER_OPT) < 1.0:
            reading = 'MODEL ignored (200)'
        elif abs(reported - TRUE_OPT) < 1.0:
            reading = 'Type-1 honoured (5000)'
        else:
            reading = f'other ({reported})'
        rows.append(dict(
            cell=cell, task=task, condition=r.get('condition'),
            variant='type1' if task.endswith('type1') else 'base',
            status=r.get('status'), score=r.get('score'),
            api_calls=r.get('api_calls'), total_tokens=r.get('total_tokens'),
            agent_seconds=r.get('agent_seconds'),
            reported_cost=reported, reading=reading,
            piecewise=marks.get('mentions_piecewise', 0),
            model_col=marks.get('mentions_model_col', 0),
            col4to6=marks.get('reads_col4to6', 0),
        ))
    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':50}{'variant':8}{'cond':16}{'score':>6}{'calls':>6}{'tok_k':>7}"
           f"{'cost':>9}  {'reading':24}{'piece':>6}{'MODELcol':>9}")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print(f"{r['cell'][:49]:50}{r['variant']:8}{r['condition']:16}"
              f"{str(r['score']):>6}{str(r['api_calls']):>6}"
              f"{(r['total_tokens'] or 0)/1000:7.0f}"
              f"{(r['reported_cost'] if r['reported_cost'] is not None else float('nan')):9.0f}"
              f"  {r['reading']:24}{r['piecewise']:6}{r['model_col']:9}")
    print()
    g = defaultdict(list)
    for r in rows:
        g[(r['variant'], r['condition'])].append(r)
    print(f"{'variant':8}{'condition':16}{'n':>3}{'mean score':>12}{'med calls':>11}"
          f"{'med tok k':>11}   readings")
    for k in sorted(g):
        rs = g[k]
        sc = [x['score'] for x in rs if x['score'] is not None]
        calls = [x['api_calls'] for x in rs if x['api_calls'] is not None]
        toks = [x['total_tokens'] for x in rs if x['total_tokens'] is not None]
        rd = defaultdict(int)
        for x in rs:
            rd[x['reading'].split(' (')[0]] += 1
        print(f"{k[0]:8}{k[1]:16}{len(rs):3}"
              f"{(statistics.mean(sc) if sc else float('nan')):12.3f}"
              f"{(statistics.median(calls) if calls else 0):11.0f}"
              f"{(statistics.median(toks)/1000 if toks else 0):11.0f}   {dict(rd)}")


if __name__ == '__main__':
    main()
