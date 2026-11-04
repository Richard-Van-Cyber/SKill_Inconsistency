#!/usr/bin/env python3
"""Analyse the lab-unit clamping paired runs.

SKILL.md's own prose ("Important") and Best Practice 4 promise a 5% tolerance
with clamping to the boundary, while the copy-pasted `convert_unit_if_needed`
block ends with `return value  # NO CLAMPING!`. The shipped CSV already contains
hundreds of values 1-5% outside their reference range, so the two readings
diverge on the shipped data alone.

The verifier only checks format, completeness and per-feature ranges, so the
decisive artifact-level measure is: how many values are still out of range?

Usage: python3 analysis_tools/lab_clamp_analyze.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import statistics
import tarfile
from collections import Counter, defaultdict

STUDY = 'experiments/labclamp-adv-20260924'
RUNS = os.path.join(STUDY, 'runs')
VERIFIER = 'tasks/lab-unit-harmonization/verifier/test_outputs.py'
INPUT = 'tasks/lab-unit-harmonization/environment/data/ckd_lab_data.csv'

REPAIRED_MARKER = re.compile(r'max_val \* 1\.05|min_val \* 0\.95')
ORIGINAL_MARKER = re.compile(r'NO CLAMPING')


def reference():
    src = open(VERIFIER).read()
    ns = {}
    exec(re.search(r'REFERENCE = \{.*?\n\}', src, re.S).group(0), {}, ns)
    return ns['REFERENCE']


def parse(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() in ('nan', 'none'):
        return None
    s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def load_output(cell):
    for root, _d, files in os.walk(cell):
        for f in files:
            if f == 'agent-artifacts.tgz':
                try:
                    with tarfile.open(os.path.join(root, f)) as t:
                        for m in t.getmembers():
                            if m.name.endswith('ckd_lab_data_harmonized.csv'):
                                return t.extractfile(m).read().decode('utf-8', 'replace')
                except Exception:
                    return None
    return None


def out_of_range(text, ref):
    if not text:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    bad = Counter(); near = Counter(); far = Counter()
    for r in rows:
        for col, rng in ref.items():
            v = parse(r.get(col))
            if v is None:
                continue
            lo, hi = rng['min'], rng['max']
            if lo <= v <= hi:
                continue
            bad[col] += 1
            if v > hi:
                rel = (v - hi) / hi if hi else 9
            else:
                rel = (lo - v) / lo if lo else 9
            (near if rel <= 0.05 else far)[col] += 1
    return dict(rows=len(rows), bad=bad, near=near, far=far)


def scan_markers(cell):
    main = None
    for root, dirs, _f in os.walk(cell):
        if os.path.basename(root).endswith('__claude-haiku') and 'api' in dirs:
            main = root
    if not main:
        return False, False
    blob = []
    for line in open(os.path.join(main, 'cli.stdout.jsonl'), errors='replace'):
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
    return bool(ORIGINAL_MARKER.search(b)), bool(REPAIRED_MARKER.search(b))


def main():
    ref = reference()
    src = open(INPUT, newline='').read()
    base = out_of_range(src, ref)
    print(f"shipped input: {base['rows']} rows, "
          f"{sum(base['bad'].values())} values out of range "
          f"({sum(base['near'].values())} within 1-5%, {sum(base['far'].values())} beyond)")
    print()

    rows = []
    for cell in sorted(os.listdir(RUNS)):
        d = os.path.join(RUNS, cell)
        rp = os.path.join(d, 'result.json')
        if not os.path.isdir(d) or not os.path.exists(rp):
            continue
        r = json.load(open(rp))
        text = load_output(d)
        oob = out_of_range(text, ref)
        orig_m, rep_m = scan_markers(d)
        rows.append(dict(
            cell=cell, condition=r.get('condition'), status=r.get('status'),
            score=r.get('score'), api_calls=r.get('api_calls'),
            total_tokens=r.get('total_tokens'),
            has_output=text is not None,
            rows_out=(oob or {}).get('rows'),
            bad_total=(sum((oob or {}).get('bad', {}).values()) if oob else None),
            bad_near=(sum((oob or {}).get('near', {}).values()) if oob else None),
            bad_far=(sum((oob or {}).get('far', {}).values()) if oob else None),
            worst_features=(sorted(((oob or {}).get('bad', {})).items(),
                                   key=lambda kv: -kv[1])[:4] if oob else None),
            used_original_snippet=orig_m, used_repaired_snippet=rep_m,
        ))
    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':46}{'score':>6}{'rows':>6}{'oob':>6}{'1-5%':>6}{'>5%':>6}"
           f"{'origSnip':>9}{'repSnip':>8}  worst")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print(f"{r['cell'][:45]:46}{str(r['score']):>6}{str(r['rows_out']):>6}"
              f"{str(r['bad_total']):>6}{str(r['bad_near']):>6}{str(r['bad_far']):>6}"
              f"{str(r['used_original_snippet']):>9}{str(r['used_repaired_snippet']):>8}"
              f"  {r['worst_features']}")
    print()
    g = defaultdict(list)
    for r in rows:
        g[r['condition']].append(r)
    print(f"{'condition':16}{'n':>3}{'mean score':>12}{'med oob':>9}"
          f"{'med 1-5% out':>14}{'copied NO-CLAMP':>17}{'copied repair':>15}")
    for k in sorted(g):
        rs = g[k]
        sc = [x['score'] for x in rs if x['score'] is not None]
        oob = [x['bad_total'] for x in rs if x['bad_total'] is not None]
        near = [x['bad_near'] for x in rs if x['bad_near'] is not None]
        print(f"{k:16}{len(rs):3}"
              f"{(statistics.mean(sc) if sc else float('nan')):12.3f}"
              f"{(statistics.median(oob) if oob else -1):9.0f}"
              f"{(statistics.median(near) if near else -1):14.0f}"
              f"{sum(1 for x in rs if x['used_original_snippet']):17}"
              f"{sum(1 for x in rs if x['used_repaired_snippet']):15}")


if __name__ == '__main__':
    main()
