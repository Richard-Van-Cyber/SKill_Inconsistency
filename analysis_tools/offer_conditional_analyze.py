#!/usr/bin/env python3
"""Analyse the offer-letter conditional-section paired runs.

task.md explicitly requires removing the `{{IF_RELOCATION}}` /
`{{END_IF_RELOCATION}}` markers. The skill doc's `handle_conditional` only fires
when BOTH markers sit in the same paragraph:

    if start_marker in text and end_marker in text:      # <- same paragraph only

The adversarial template puts them in different paragraphs, so a solution that
copies that loop leaves both markers behind and fails
`test_conditional_section`.

Decisive artifact-level evidence: does the produced .docx still contain the
markers, and are RELOCATION_AMOUNT / RELOCATION_DAYS still present?

Usage: python3 analysis_tools/offer_conditional_analyze.py [study_dir]
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
import tarfile
import zipfile
from collections import defaultdict

STUDY = sys.argv[1] if len(sys.argv) > 1 else 'experiments/adv02-offer-20260924'
RUNS = os.path.join(STUDY, 'runs')
EMPLOYEE = 'tasks/offer-letter-generator/environment/employee_data.json'

DATA = json.load(open(EMPLOYEE))
AMOUNT, DAYS = DATA['RELOCATION_AMOUNT'], DATA['RELOCATION_DAYS']


def docx_text(blob):
    with zipfile.ZipFile(blob) as z:
        xml = z.read('word/document.xml').decode('utf-8', 'replace')
    return ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', xml))


def read_output(cell):
    for root, _d, files in os.walk(cell):
        for f in files:
            if f == 'agent-artifacts.tgz':
                try:
                    with tarfile.open(os.path.join(root, f)) as t:
                        for m in t.getmembers():
                            if m.name.endswith('offer_letter_filled.docx'):
                                import io
                                return docx_text(io.BytesIO(t.extractfile(m).read()))
                except Exception:
                    return None
    return None


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
        txt = read_output(d)
        rows.append(dict(
            cell=cell, condition=r.get('condition'), status=r.get('status'),
            score=r.get('score'), api_calls=r.get('api_calls'),
            total_tokens=r.get('total_tokens'),
            has_docx=txt is not None,
            if_marker=bool(txt and '{{IF_RELOCATION}}' in txt),
            endif_marker=bool(txt and '{{END_IF_RELOCATION}}' in txt),
            amount_kept=bool(txt and AMOUNT in txt),
            days_kept=bool(txt and DAYS in txt),
            leftover_placeholders=(sorted(set(re.findall(r'\{\{[A-Z_]+\}\}', txt)))[:6]
                                   if txt else None),
        ))
    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':52}{'score':>6}{'docx':>6}{'IFmark':>7}{'ENDmark':>8}"
           f"{'AMT':>5}{'DAYS':>6}  other placeholders")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        print(f"{r['cell'][:51]:52}{str(r['score']):>6}{str(r['has_docx']):>6}"
              f"{str(r['if_marker']):>7}{str(r['endif_marker']):>8}"
              f"{str(r['amount_kept']):>5}{str(r['days_kept']):>6}  "
              f"{r['leftover_placeholders']}")
    print()
    g = defaultdict(list)
    for r in rows:
        g[r['condition']].append(r)
    print(f"{'condition':16}{'n':>3}{'mean score':>12}{'markers removed':>17}"
          f"{'content kept':>14}")
    for k in sorted(g):
        rs = g[k]
        sc = [x['score'] for x in rs if x['score'] is not None]
        print(f"{k:16}{len(rs):3}"
              f"{(statistics.mean(sc) if sc else float('nan')):12.3f}"
              f"{sum(1 for x in rs if x['has_docx'] and not x['if_marker'] and not x['endif_marker']):17}"
              f"{sum(1 for x in rs if x['amount_kept'] and x['days_kept']):14}")


if __name__ == '__main__':
    main()
