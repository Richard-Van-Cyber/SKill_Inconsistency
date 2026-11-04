#!/usr/bin/env python3
"""For the Recover class: what exactly did each arm do? Is the Fixed arm a valid control?"""
import csv, json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_v3 as A

OUT = os.environ.get('WSOUT', '/home/user/project/RQ3/analysis')
rows = list(csv.DictReader(open(OUT + '/labels_v3.csv')))
rec = [r for r in rows if r['response'] == 'Recover -> success']
idx = {}
for r in csv.DictReader(open(A.MANIFEST)):
    if r.get('arm') in ('OriginalSkill', 'FixedSkill'):
        idx[(r['axis'], r['task'], r['arm'], r['trial'])] = A.EXP + r['rel_path'] + '/'

c = collections.Counter()
detail = []
for r in rec:
    d = json.load(open('%s/%s.json' % (A.DESC, r['task'])))
    co = idx.get((r['axis'], r['task'], 'OriginalSkill', r['trial']))
    cf = idx.get((r['axis'], r['task'], 'FixedSkill', r['trial']))
    so = A.analyze(co, d) if co else {}
    sf = A.analyze(cf, d) if cf else {}
    o_read, f_read = so.get('skill_read'), sf.get('skill_read')
    o_exec, f_exec = so.get('exec_changed_file'), sf.get('exec_changed_file')
    o_ship, f_ship = so.get('ship_anchor_agent', 0), sf.get('ship_anchor_agent', 0)
    o_man, f_man = so.get('manifested'), sf.get('manifested')
    c['total'] += 1
    c['fixed_read' if f_read else 'fixed_NO_read'] += 1
    c['fixed_exec' if f_exec else 'fixed_NO_exec'] += 1
    c['fixed_manifested' if f_man else 'fixed_not_manifested'] += 1
    c['fixed_ship_anchor' if f_ship else 'fixed_no_ship_anchor'] += 1
    c['orig_read' if o_read else 'orig_NO_read'] += 1
    c['orig_exec' if o_exec else 'orig_NO_exec'] += 1
    detail.append((r['task'], r['axis'], r['trial'], f_read, f_exec, f_ship, f_man,
                   r['score_original'], r['score_fixed']))

print('RECOVER class, n =', len(rec))
for k in sorted(c):
    print('  %-24s %d' % (k, c[k]))
print()
print('=== Fix arm did NOT read the skill, or did NOT execute the changed file:')
odd = [x for x in detail if (not x[3]) or (not x[4])]
print('  count:', len(odd))
for t, a, tr, fr, fe, fs, fm, so, sf in odd[:25]:
    print('  %-30s %-9s %s  fix_read=%s fix_exec=%s fix_man=%s  scoreO=%s scoreF=%s'
          % (t, a, tr, fr, fe, fm, so, sf))
