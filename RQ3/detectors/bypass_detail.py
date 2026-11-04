#!/usr/bin/env python3
"""Per-pair detail for the Bypass category: does the Fixed arm use the inconsistent element?"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_v3 as A

rows = list(csv.DictReader(open(os.environ.get('WSOUT', '/home/user/project/RQ3/analysis') + '/labels_v3.csv')))
by = [r for r in rows if r['response'] == 'Bypass']
idx = {}
for r in csv.DictReader(open(A.MANIFEST)):
    if r.get('arm') in ('OriginalSkill', 'FixedSkill'):
        idx[(r['axis'], r['task'], r['arm'], r['trial'])] = A.EXP + r['rel_path'] + '/'

print('task|axis|trial|scoreO|scoreF|fixed_used|fixed_exec_changed|fixed_read')
agg = {'ties': 0, 'fix_higher': 0, 'orig_higher': 0,
       'tie_fix_used': 0, 'tie_fix_unused': 0, 'fh_fix_used': 0, 'oh_fix_used': 0}
for r in sorted(by, key=lambda x: (x['task'], x['axis'], x['trial'])):
    d = json.load(open('%s/%s.json' % (A.DESC, r['task'])))
    cf = idx.get((r['axis'], r['task'], 'FixedSkill', r['trial']))
    sf = A.analyze(cf, d) if cf else {}
    so, sfn = float(r['score_original']), float(r['score_fixed'])
    f_used = bool(sf.get('used'))
    if abs(so - sfn) < 1e-9:
        agg['ties'] += 1
        agg['tie_fix_used' if f_used else 'tie_fix_unused'] += 1
    elif sfn > so:
        agg['fix_higher'] += 1
        agg['fh_fix_used'] += 1 if f_used else 0
    else:
        agg['orig_higher'] += 1
        agg['oh_fix_used'] += 1 if f_used else 0
    print('%s|%s|%s|%.3f|%.3f|%s|%s|%s' % (r['task'], r['axis'], r['trial'], so, sfn,
                                            f_used, sf.get('exec_changed_file'), sf.get('skill_read')))
print()
print('SUMMARY', json.dumps(agg))
