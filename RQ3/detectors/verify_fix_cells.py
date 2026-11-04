#!/usr/bin/env python3
"""Open the Fixed-arm trajectories of the four 'invalid control' pairs and check whether the
flags are real behaviour or a resolution/parse failure."""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_v3 as A

PAIRS = [('scheduled-task-arg-contract', 'deepseek', 'r3'),
         ('csv-report-offline', 'haiku', 'r2'),
         ('graph-merge', 'qwen', 'r1'),
         ('scheduled-task-arg-contract', 'qwen', 'r2')]

rows = list(csv.DictReader(open(A.MANIFEST)))
for task, axis, trial in PAIRS:
    print('=' * 90)
    print('PAIR %s / %s / %s' % (task, axis, trial))
    for arm in ('OriginalSkill', 'FixedSkill'):
        hits = [r for r in rows if r['axis'] == axis and r['task'] == task
                and r['arm'] == arm and r['trial'] == trial]
        print('  [%s] manifest rows: %d' % (arm, len(hits)))
        for h in hits:
            cell = A.EXP + h['rel_path'] + '/'
            f = cell + 'cli.stdout.jsonl'
            res = os.path.exists(cell + 'result.json')
            exists = os.path.exists(f)
            nl = sum(1 for _ in open(f, errors='ignore')) if exists else -1
            d = json.load(open('%s/%s.json' % (A.DESC, task)))
            sig = A.analyze(cell, d)
            o = sig['outcome']
            print('     path=%s' % h['rel_path'])
            print('       file_exists=%s lines=%s result.json=%s' % (exists, nl, res))
            print('       parsed_turns=%d skill_read=%s exec_changed=%s ship_agent=%d '
                  'used=%s manifested=%s score=%s'
                  % (sig['n_turns'], sig['skill_read'], sig['exec_changed_file'],
                     sig['ship_anchor_agent'], sig['used'], sig['manifested'], o.get('score')))
