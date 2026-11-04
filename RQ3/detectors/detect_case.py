#!/usr/bin/env python3
"""RQ3 detector v2 - label a paired case (task, model, trial): Original vs Fixed.

Design decisions forced by the v1 experiments:
  * "saw the anchor" != "used the anchor".  Anchor occurrences are counted separately in
    (a) agent-authored actions (Bash commands, Write/Edit payloads) and (b) tool results.
    Only (a) -- or invoking a file that the repair modified -- counts as use.
  * Verifier check names are normalised: the verifier defines check_foo, pytest reports ::test_foo,
    so the comparison is made on the canonical suffix.
  * Response and outcome are separate fields; a response is attributed to the inconsistency only
    when the peer (Fixed) arm does not show the same behaviour.

Usage: detect_case.py --desc <descriptor.json> --runs <dir> ... --task T --model M [--trial r1]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re

ERR_MARK = re.compile(r'\b(Error|ERROR|Traceback|No such file|not found|command not found|'
                      r'unrecognized|unexpected|invalid|failed|FAILED|cannot|'
                      r'Missing required|exit code [1-9])\b')
EXP = os.environ.get('WSEXP', '/home/user/project/experiments/')
SKILL_PATH = re.compile(r'/(?:app|home/agent/\.claude)/skills/')


def canon(name: str) -> str:
    n = name.split('::')[-1].split('[')[0]
    for pre in ('test_check_', 'test_', 'check_'):
        if n.startswith(pre):
            return n[len(pre):].strip()
    return n.strip()


def load_cell(cell: str):
    events, agent, result = [], [], []
    p = os.path.join(cell, 'cli.stdout.jsonl')
    for line in open(p, errors='ignore') if os.path.exists(p) else []:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get('type') not in ('assistant', 'user'):
            continue
        for blk in ((d.get('message') or {}).get('content') or []):
            if not isinstance(blk, dict):
                continue
            if blk.get('type') == 'tool_use':
                arg = json.dumps(blk.get('input') or {}, ensure_ascii=False)
                events.append({'turn': len(events), 'tool': blk.get('name'), 'arg': arg, 'err': False})
                agent.append(arg)
            elif blk.get('type') == 'tool_result':
                c = blk.get('content')
                if isinstance(c, list):
                    c = ' '.join(str(x.get('text', '')) if isinstance(x, dict) else str(x) for x in c)
                c = str(c or '')
                result.append(c)
                if events:
                    events[-1]['err'] = events[-1]['err'] or bool(blk.get('is_error')) \
                        or bool(ERR_MARK.search(c[:600]))
    return events, '\n'.join(agent), '\n'.join(result)


def failed_checks(cell: str) -> set:
    p = os.path.join(cell, 'benchflow/verifier/ctrf.json')
    if not os.path.exists(p):
        return set()
    try:
        tests = (json.load(open(p)).get('results') or {}).get('tests') or []
    except Exception:
        return set()
    return {canon(t.get('name', '')) for t in tests if t.get('status') != 'passed'}


def outcome(cell: str) -> dict:
    p = os.path.join(cell, 'result.json')
    if not os.path.exists(p):
        return {}
    d = json.load(open(p))
    return {k: d.get(k) for k in ('score', 'total_tokens', 'api_calls', 'num_turns',
                                  'agent_seconds', 'termination_reason')}


def signature(cell: str, desc: dict, transcript=False):
    ev, agent, result = load_cell(cell)
    strip = '`"\''
    ship = [a.strip(strip) for a in desc.get('anchors_shipped_only', []) if len(a) >= 5]
    fix = [a.strip(strip) for a in desc.get('anchors_fixed_only', []) if len(a) >= 5]
    bases = [os.path.basename(f) for f in desc.get('changed_files', [])]
    reads = [e for e in ev if e['tool'] in ('Read', 'Grep', 'Glob', 'Bash', 'Skill')
             and SKILL_PATH.search(e['arg'])]
    changed_used = [e['turn'] for e in ev if any(b and b in e['arg'] for b in bases)]
    used_ship = sorted({a for a in ship if a in agent})
    seen_ship = sorted({a for a in ship if a in result})
    used_fix = sorted({a for a in fix if a in agent})
    first_use = min(changed_used) if changed_used else (
        next((e['turn'] for e in ev if any(a in e['arg'] for a in used_ship)), None) if used_ship else None)
    errs_after = [e for e in ev if e['err'] and first_use is not None and e['turn'] >= first_use]
    if transcript:
        print('      transcript (first 18 turns):')
        for e in ev[:18]:
            print('        %2d %-6s%s %s' % (e['turn'], e['tool'], '!' if e['err'] else ' ', e['arg'][:96]))
    return {'cell': cell, 'n_tools': len(ev), 'skill_read': bool(reads),
            'first_skill_read_turn': reads[0]['turn'] if reads else None,
            'changed_file_used': changed_used[:5], 'used_shipped_anchor': used_ship,
            'seen_shipped_anchor_in_output': seen_ship, 'used_fixed_anchor': used_fix,
            'errors_after_first_use': len(errs_after),
            'failed_checks': sorted(failed_checks(cell)), 'outcome': outcome(cell)}


def label(orig: dict, fixed: dict, desc: dict) -> dict:
    rel = {canon(c) for c in (desc.get('related_checks') or [])}
    rel_fail_o = sorted(set(orig['failed_checks']) & rel)
    rel_fail_f = sorted(set(fixed['failed_checks']) & rel)
    used = bool(orig['used_shipped_anchor']) or bool(orig['changed_file_used'])
    if not orig['skill_read'] and fixed['skill_read']:
        resp = 'Bypass (induced by inconsistency)'
    elif not orig['skill_read'] and not fixed['skill_read']:
        resp = 'Bypass (both arms)'
    elif used and rel_fail_o and not rel_fail_f:
        resp = 'Follow -> failure'
    elif used and rel_fail_o and rel_fail_f:
        resp = 'Used -> both arms fail related checks'
    elif used and (orig['errors_after_first_use'] or orig['used_fixed_anchor']):
        resp = 'Recover -> success with overhead'
    elif not used:
        resp = 'Not used (no exposure)'
    else:
        resp = 'Used, outcome unchanged'
    so, sf = orig['outcome'].get('score'), fixed['outcome'].get('score')
    return {'exposed': bool(orig['skill_read'] and used), 'response': resp,
            'related_fail_original': rel_fail_o, 'related_fail_fixed': rel_fail_f,
            'paired_contrast_available': bool(rel_fail_o and not rel_fail_f),
            'delta_score': (sf - so) if (so is not None and sf is not None) else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--desc', required=True)
    ap.add_argument('--runs', nargs='*', default=[])
    ap.add_argument('--manifest', default=None,
                    help='collection manifest.csv; resolves (axis, task, arm, trial) -> cell path')
    ap.add_argument('--task', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--trial', default='r1')
    ap.add_argument('--transcript', action='store_true')
    a = ap.parse_args()
    desc = json.load(open(a.desc))
    cells = {}
    if a.manifest:
        for r in csv.DictReader(open(a.manifest)):
            if (r['axis'] == a.model and r['task'] == a.task and r['arm'] in
                    ('OriginalSkill', 'FixedSkill') and r['trial'] == a.trial):
                cells.setdefault(r['arm'], EXP + r['rel_path'] + '/')
    if not cells:
        for root in a.runs:
            for arm in ('OriginalSkill', 'FixedSkill'):
                h = glob.glob('%s/%s__%s__%s/*/' % (root, a.task, arm, a.trial))
                cells.setdefault(arm, h[0] if h else None)
    print('=== %s [%s] / %s / %s' % (a.task, ','.join(desc.get('types') or []) or desc.get('legacy_type') or '?',
                                     a.model, a.trial))
    if not all(cells.values()):
        print('  missing arms:', cells)
        return 1
    sig = {k: signature(v, desc, a.transcript) for k, v in cells.items()}
    lab = label(sig['OriginalSkill'], sig['FixedSkill'], desc)
    for arm in ('OriginalSkill', 'FixedSkill'):
        s = sig[arm]
        o = s['outcome']
        print('  [%-14s] score=%s tok=%s calls=%s secs=%s' % (arm, o.get('score'), o.get('total_tokens'),
                                                              o.get('api_calls'), o.get('agent_seconds')))
        print('      skill_read=%s changed_file_used=%s used_shipped=%d used_fixed=%d errors_after_use=%d' %
              (s['skill_read'], bool(s['changed_file_used']), len(s['used_shipped_anchor']),
               len(s['used_fixed_anchor']), s['errors_after_first_use']))
        if s['failed_checks']:
            print('      failed checks (%d): %s' % (len(s['failed_checks']), s['failed_checks'][:5]))
    print('  --> exposed=%s response=%s paired_only_original_fails=%s delta_score=%s' %
          (lab['exposed'], lab['response'], lab['paired_contrast_available'], lab['delta_score']))
    os.makedirs('RQ3/analysis', exist_ok=True)
    json.dump({'task': a.task, 'model': a.model, 'trial': a.trial, 'types': desc.get('types'),
               'signature': sig, 'labels': lab},
              open('RQ3/analysis/label_%s__%s__%s.json' % (a.task, a.model, a.trial), 'w'),
              indent=1, ensure_ascii=False, default=str)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
