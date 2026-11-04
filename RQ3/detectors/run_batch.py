#!/usr/bin/env python3
"""RQ3 step 1 — batch-label every paired cell and summarise the distribution.

Reads descriptors + the collection manifest, labels (task, model, trial) for all tasks, and writes
RQ3/analysis/labels.csv plus a printed distribution of exposure / response / paired-contrast.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect_case as D  # noqa: E402

EXP = os.environ.get('WSEXP', '/home/user/project/experiments/')
MANIFEST = os.environ.get('WSMANIFEST', EXP + 'wildskills-collection/manifest.csv')
DESC = os.environ.get('WSDESC', '/home/user/project/RQ3/descriptors')
OUT = os.environ.get('WSOUT', '/home/user/project/RQ3/analysis')

rows = list(csv.DictReader(open(MANIFEST)))
idx = {}
for r in rows:
    if r['arm'] in ('OriginalSkill', 'FixedSkill'):
        idx[(r['axis'], r['task'], r['arm'], r['trial'])] = EXP + r['rel_path'] + '/'

out, seen = [], set()
for (axis, task, arm, trial) in list(idx):
    if (axis, task, trial) in seen:
        continue
    seen.add((axis, task, trial))
    co, cf = idx.get((axis, task, 'OriginalSkill', trial)), idx.get((axis, task, 'FixedSkill', trial))
    dp = os.path.join(DESC, task + '.json')
    if not (co and cf and os.path.exists(dp) and os.path.exists(co + 'result.json')):
        continue
    desc = json.load(open(dp))
    so, sf = D.signature(co, desc), D.signature(cf, desc)
    lab = D.label(so, sf, desc)
    types = [t.strip() for t in (desc.get('types') or []) if t.strip()] or [desc.get('legacy_type') or '?']
    out.append({
        'task': task, 'axis': axis, 'trial': trial, 'batch': desc.get('batch'),
        'type_primary': types[0], 'n_types': len(types),
        'exposed': lab['exposed'], 'response': lab['response'],
        'paired_only_original_fails': lab['paired_contrast_available'],
        'related_fail_original': len(lab['related_fail_original']),
        'related_fail_fixed': len(lab['related_fail_fixed']),
        'skill_read_original': so['skill_read'], 'used_shipped': len(so['used_shipped_anchor']),
        'changed_file_used': bool(so['changed_file_used']),
        'errors_after_use_original': so['errors_after_first_use'],
        'score_original': so['outcome'].get('score'), 'score_fixed': sf['outcome'].get('score'),
        'delta_score': lab['delta_score'],
        'tok_original': so['outcome'].get('total_tokens'), 'tok_fixed': sf['outcome'].get('total_tokens'),
        'secs_original': so['outcome'].get('agent_seconds'), 'secs_fixed': sf['outcome'].get('agent_seconds'),
    })

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'labels.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)

print('paired cells labelled:', len(out))
print('  exposed        :', sum(1 for r in out if r['exposed'] is True), '/', len(out))
print('  response distribution:')
for k, v in collections.Counter(r['response'] for r in out).most_common():
    print('    %-42s %d' % (k, v))
print('  type x response (top combinations):')
c = collections.Counter((r['type_primary'], r['response']) for r in out)
for (t, resp), k in c.most_common(12):
    print('    %-46s %-38s %d' % (t, resp, k))
print('  by axis:')
for ax in sorted({r['axis'] for r in out}):
    sub = [r for r in out if r['axis'] == ax]
    d = [r['delta_score'] for r in sub if r['delta_score'] is not None]
    import statistics
    print('    %-9s n=%d  exposed=%d  mean delta_score=%+.3f  followed_to_failure=%d' % (
        ax, len(sub), sum(1 for r in sub if r['exposed'] is True),
        statistics.mean(d) if d else 0,
        sum(1 for r in sub if r['response'].startswith('Follow'))))
