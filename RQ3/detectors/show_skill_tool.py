#!/usr/bin/env python3
"""Show real Skill-tool invocations vs path-based reads, side by side."""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_v3 as A

rows = list(csv.DictReader(open(A.MANIFEST)))
idx = A.build_index(rows, principled=True)
shown_tool, shown_path = 0, 0
for k, cell in idx.items():
    if not os.path.exists(cell + 'cli.stdout.jsonl'):
        continue
    for t in A.parse(cell):
        if t['tool'] == 'Skill' and shown_tool < 3:
            print('Skill tool  -> %s' % t['arg'][:160])
            shown_tool += 1
        elif t['tool'] in ('Read', 'Bash', 'Grep') and 'skills/' in t['arg'] and shown_path < 3:
            print('path-based  -> %s: %s' % (t['tool'], t['arg'][:150]))
            shown_path += 1
    if shown_tool >= 3 and shown_path >= 3:
        break
