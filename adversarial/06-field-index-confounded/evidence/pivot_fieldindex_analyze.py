#!/usr/bin/env python3
"""Analyse the pivot field-index paired runs.

The skill's xlsx/SKILL.md two-dimensional pivot example hard-codes
`pivot.pivotFields[1]` / `RowColField(x=1)` and labels index 1 "Quarter", while
its own cache-field list and the task's SourceData put Quarter elsewhere. The
verifier asserts the column field of the "State Income Quartile" pivot contains
"quarter". Decisive evidence is therefore the pivot's actual column field.

Usage: python3 analysis_tools/pivot_fieldindex_analyze.py
"""
from __future__ import annotations

import io
import json
import os
import re
import statistics
import tarfile
import zipfile
from collections import defaultdict

STUDY = 'experiments/pivot-fieldindex-adv-20260924'
RUNS = os.path.join(STUDY, 'runs')

LITERAL_INDEX = re.compile(r'pivotFields\[1\]|RowColField\(x=1\)|fld=1\b')


def find_main(cell):
    for root, dirs, _f in os.walk(cell):
        if os.path.basename(root).endswith('__claude-haiku') and 'api' in dirs:
            return root
    return None


def extract_xlsx(cell):
    for root, _d, files in os.walk(cell):
        for f in files:
            if f == 'agent-artifacts.tgz':
                try:
                    with tarfile.open(os.path.join(root, f)) as t:
                        for m in t.getmembers():
                            if m.name.endswith('.xlsx'):
                                return t.extractfile(m).read()
                except Exception:
                    return None
    return None


def pivot_report(data):
    """Return (col_field_names, all_cache_names, sheet_names)."""
    if not data:
        return None, None, None
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
    cache_names = []
    for ws in wb.worksheets:
        for pc in getattr(ws, '_pivots', []) or []:
            try:
                cache = pc.cache
                names = [getattr(cf, 'name', None) for cf in cache.cacheFields]
                cache_names = names
                col_idx = [getattr(cf, 'x', None) for cf in (pc.colFields or [])]
                col_names = [names[i] if i is not None and 0 <= i < len(names) else None
                             for i in col_idx]
                return col_names, names, wb.sheetnames
            except Exception:
                pass
    return [], cache_names, wb.sheetnames


def main():
    rows = []
    for cell in sorted(os.listdir(RUNS)):
        d = os.path.join(RUNS, cell)
        rp = os.path.join(d, 'result.json')
        if not os.path.isdir(d) or not os.path.exists(rp):
            continue
        r = json.load(open(rp))
        data = extract_xlsx(d)
        col_names, cache_names, sheets = pivot_report(data)
        main_dir = find_main(d)
        literal = False
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
            literal = bool(LITERAL_INDEX.search("\n".join(blob)))
        col_ok = bool(col_names) and any(
            c and 'quarter' in c.lower() for c in col_names)
        rows.append(dict(
            cell=cell, condition=r.get('condition'), status=r.get('status'),
            score=r.get('score'), api_calls=r.get('api_calls'),
            total_tokens=r.get('total_tokens'),
            has_xlsx=data is not None,
            col_fields=col_names, cache_fields=cache_names, sheets=sheets,
            col_field_ok=col_ok, used_literal_index=literal,
        ))
    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':46}{'score':>6}{'xlsx':>6}{'colOK':>7}{'literalIdx':>11}"
           f"  colFields")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print(f"{r['cell'][:45]:46}{str(r['score']):>6}{str(r['has_xlsx']):>6}"
              f"{str(r['col_field_ok']):>7}{str(r['used_literal_index']):>11}"
              f"  {r['col_fields']}")
    print()
    g = defaultdict(list)
    for r in rows:
        g[r['condition']].append(r)
    print(f"{'condition':16}{'n':>3}{'mean score':>12}{'xlsx produced':>15}"
          f"{'colField quarter':>18}{'used literal idx':>18}")
    for k in sorted(g):
        rs = g[k]
        sc = [x['score'] for x in rs if x['score'] is not None]
        print(f"{k:16}{len(rs):3}"
              f"{(statistics.mean(sc) if sc else float('nan')):12.3f}"
              f"{sum(1 for x in rs if x['has_xlsx']):15}"
              f"{sum(1 for x in rs if x['col_field_ok']):18}"
              f"{sum(1 for x in rs if x['used_literal_index']):18}")


if __name__ == '__main__':
    main()
