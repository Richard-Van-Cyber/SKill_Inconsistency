#!/usr/bin/env python3
"""Recover class: how much of it is a clean counterfactual? Strict control = the Fixed arm
read the skill, executed the changed file, and did not author the shipped-only form."""
import csv, json, os, sys, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_v3 as A

OUT = os.environ.get('WSOUT', '/home/user/project/RQ3/analysis')
rows = list(csv.DictReader(open(OUT + '/labels_v3.csv')))
idx = {}
for r in csv.DictReader(open(A.MANIFEST)):
    if r.get('arm') in ('OriginalSkill', 'FixedSkill'):
        idx[(r['axis'], r['task'], r['arm'], r['trial'])] = A.EXP + r['rel_path'] + '/'

def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else 0.0

def run(sel_name, sel):
    n = len(sel)
    if not n:
        print(sel_name, 'n=0'); return
    ds = mean([x['ds'] for x in sel]); dt = mean([x['dt'] for x in sel])
    print('  %-34s n=%-4d dScore=%+.3f  dTok/run=%+.0fk  scoreO=%.3f scoreF=%.3f'
          % (sel_name, n, ds, dt / 1000, mean([x['so'] for x in sel]), mean([x['sf'] for x in sel])))

loose, strict, invalid = [], [], []
for r in rows:
    if r['response'] != 'Recover -> success':
        continue
    d = json.load(open('%s/%s.json' % (A.DESC, r['task'])))
    co = idx.get((r['axis'], r['task'], 'OriginalSkill', r['trial']))
    cf = idx.get((r['axis'], r['task'], 'FixedSkill', r['trial']))
    so = A.analyze(co, d) if co else {}
    sf = A.analyze(cf, d) if cf else {}
    rec = {'task': r['task'], 'axis': r['axis'], 'trial': r['trial'],
           'ds': float(r['delta_score']) if r['delta_score'] not in ('', 'None') else None,
           'dt': (float(r['tok_original']) - float(r['tok_fixed']))
                 if r['tok_original'] and r['tok_fixed'] else None,
           'so': float(r['score_original']), 'sf': float(r['score_fixed'])}
    loose.append(rec)
    f_read, f_exec = bool(sf.get('skill_read')), bool(sf.get('exec_changed_file'))
    f_ship = sf.get('ship_anchor_agent', 0)
    if f_read and f_exec and f_ship == 0:
        strict.append(rec)
    if (not f_read) or (not f_exec):
        invalid.append(rec)

print('RECOVER class split by whether the Fixed arm is a clean control:')
run('loose (as reported)', loose)
run('clean control (read+exec+no ship)', strict)
run('invalid control (fix miss read/exec)', invalid)
print()
print('invalid-control pairs:')
for x in invalid:
    print('   %-30s %-9s %s  scoreO=%.3f scoreF=%.3f' % (x['task'], x['axis'], x['trial'], x['so'], x['sf']))
