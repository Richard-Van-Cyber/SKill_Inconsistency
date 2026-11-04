#!/usr/bin/env python3
"""Analyse the earthquake adversarial paired runs.

Reads experiments/earthquake-adv-20260924/runs/<cell>/... and reports, per cell:
  * reward / status / efficiency (api_calls, tokens, agent seconds)
  * whether the plate-selection idiom the skill's SKILL.md showed was used, and
    whether it was the one that raises KeyError on this data variant
  * the actual KeyError text, if any

Trigger evidence is textual and deliberately explicit: the skill document
contains three mutually incompatible ways to select the Pacific plate
(`Plates["Name"]`, `Plates["PlateName"]`, `Plates["Code"] == "PA"`), and which
one blows up depends only on the data variant.

Usage: python3 analysis_tools/eq_adv_analyze.py
"""
from __future__ import annotations

import json
import os
import re
import statistics
from collections import Counter, defaultdict

STUDY = 'experiments/earthquake-adv-20260924'
RUNS = os.path.join(STUDY, 'runs')

# idioms in the skill document
IDIOMS = {
    'name_col':        re.compile(r'\[\s*[\'"]Name[\'"]\s*\]'),
    'platename_col':   re.compile(r'\[\s*[\'"]PlateName[\'"]\s*\]'),
    'code_PA':         re.compile(r'\[\s*[\'"]Code[\'"]\s*\]\s*==\s*[\'"]PA[\'"]'),
}
KEYERR = re.compile(r"KeyError[^\n]{0,120}")


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def scan_cell(cell_dir):
    """Walk the agent transcript and collect idiom / error evidence."""
    hits = Counter()
    keyerrors = Counter()
    transcript = None
    for root, _dirs, files in os.walk(cell_dir):
        for f in files:
            if f == 'cli.stdout.jsonl':
                transcript = os.path.join(root, f)
                break
        if transcript:
            break
    if not transcript:
        return hits, keyerrors, 0

    main = None
    for root, _dirs, files in os.walk(cell_dir):
        if os.path.basename(root).endswith('__claude-haiku') and 'api' in _dirs:
            main = root
    blob_parts = []
    path = os.path.join(main, 'cli.stdout.jsonl') if main else transcript
    with open(path, errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            blob_parts.append(line)
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get('type') == 'assistant':
                for c in (o.get('message') or {}).get('content') or []:
                    if isinstance(c, dict) and c.get('type') == 'tool_use':
                        s = json.dumps(c.get('input') or {}, ensure_ascii=False)
                        for k, rx in IDIOMS.items():
                            if rx.search(s):
                                hits[k] += 1
            elif o.get('type') == 'user':
                for c in (o.get('message') or {}).get('content') or []:
                    if isinstance(c, dict) and c.get('type') == 'tool_result':
                        t = text_of(c.get('content'))
                        for m in KEYERR.finditer(t):
                            keyerrors[m.group(0)[:100]] += 1
    blob = "\n".join(blob_parts)
    for k, rx in IDIOMS.items():
        # also count occurrences in the whole transcript (agent's own files)
        n = len(rx.findall(blob))
        if n:
            hits[k] = max(hits[k], n)
    return hits, keyerrors, len(blob_parts)


def main():
    if not os.path.isdir(RUNS):
        raise SystemExit(f'no runs at {RUNS}')
    rows = []
    for cell in sorted(os.listdir(RUNS)):
        d = os.path.join(RUNS, cell)
        if not os.path.isdir(d):
            continue
        res_p = os.path.join(d, 'result.json')
        if not os.path.exists(res_p):
            continue
        r = json.load(open(res_p))
        hits, kerr, nlines = scan_cell(d)
        task = r.get('task', '')
        cond = r.get('condition', '')
        rep = r.get('repeat')
        rows.append(dict(
            cell=cell, task=task, condition=cond, repeat=rep,
            variant='adv' if task.endswith('-adv') else 'shipped',
            status=r.get('status'), score=r.get('score'),
            api_calls=r.get('api_calls'), total_tokens=r.get('total_tokens'),
            agent_seconds=r.get('agent_seconds'),
            used_name=hits.get('name_col', 0),
            used_platename=hits.get('platename_col', 0),
            used_code=hits.get('code_PA', 0),
            keyerrors=sum(kerr.values()),
            keyerror_top=(kerr.most_common(1)[0][0] if kerr else ''),
            error=r.get('error'),
        ))

    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':54}{'variant':9}{'cond':16}{'score':>6}{'calls':>6}"
           f"{'tok_k':>7}{'Name':>6}{'PlateNm':>8}{'Code':>5}{'KeyErr':>7}")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print(f"{r['cell'][:53]:54}{r['variant']:9}{r['condition']:16}"
              f"{str(r['score']):>6}{str(r['api_calls']):>6}"
              f"{(r['total_tokens'] or 0)/1000:7.0f}{r['used_name']:6}{r['used_platename']:8}"
              f"{r['used_code']:5}{r['keyerrors']:7}")

    print()
    groups = defaultdict(list)
    for r in rows:
        groups[(r['variant'], r['condition'])].append(r)
    print(f"{'variant':9}{'condition':16}{'n':>3}{'mean score':>12}{'med calls':>11}"
          f"{'med tok k':>11}{'med s':>8}{'Name idiom':>12}")
    for k in sorted(groups):
        g = groups[k]
        scores = [x['score'] for x in g if x['score'] is not None]
        calls = [x['api_calls'] for x in g if x['api_calls'] is not None]
        toks = [x['total_tokens'] for x in g if x['total_tokens'] is not None]
        secs = [x['agent_seconds'] for x in g if x['agent_seconds'] is not None]
        print(f"{k[0]:9}{k[1]:16}{len(g):3}"
              f"{(statistics.mean(scores) if scores else float('nan')):12.3f}"
              f"{(statistics.median(calls) if calls else 0):11.0f}"
              f"{(statistics.median(toks)/1000 if toks else 0):11.0f}"
              f"{(statistics.median(secs) if secs else 0):8.0f}"
              f"{sum(1 for x in g if x['used_name']):12}")


if __name__ == '__main__':
    main()
