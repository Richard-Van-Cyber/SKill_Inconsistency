#!/usr/bin/env python3
"""RQ3 trajectory audit (v3) -- two-level framework.

Exposure is *contact*: the agent read the skill.  Given exposure, the response is

    Bypass   -- the skill was read but its inconsistent element was not used
    Follow   -- the inconsistent behaviour was adopted and reached the artifact
    Recover  -- it was adopted, fired, and was corrected before delivery

A trajectory that never reads the skill is Unused and lies outside the chain.

Every label rests on a concrete, auditable signal:
    skill read          -> a Read/Grep/Glob/Bash/Skill action on a skill path
    used                -> executed a file the repair changed, or authored a shipped-only anchor
    manifested          -> a shipped-only anchor surfaced in tool output, or an error occurred
                           while executing the changed file
    delivered wrong     -> a verifier check tied to the incident fails in this arm

Cost of the incident is measured *inside* the trajectory, as the segment from the turn the
incident first manifested to the turn the agent settled on the corrected form (Recover) or to the
end of the run (Follow); tokens are per-turn, from the message usage records.

Writes labels_v3.csv and prints the three sub-RQ tables.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import re
import statistics
import sys

EXP = os.environ.get('WSEXP', '/home/user/project/experiments/')
DESC = os.environ.get('WSDESC', '/home/user/project/RQ3/descriptors')
OUT = os.environ.get('WSOUT', '/home/user/project/RQ3/analysis')
MANIFEST = os.environ.get('WSMANIFEST', EXP + 'wildskills-collection/manifest.csv')
# standard design trials; legacy batches re-ran some tasks with extra trials (r4-r6), which are
# excluded here so that every model contributes the same 147 pairs.
TRIALS = {t.strip() for t in os.environ.get('WSTRIALS', 'r1,r2,r3').split(',') if t.strip()}

SKILL_PATH = re.compile(r'/(?:app|home/agent/\.claude|root/\.claude)/skills/')
ERR_WORDS = re.compile(r'\b(Error|ERROR|Traceback|No such file|not found|command not found|'
                       r'unrecognized|unexpected|invalid|failed|FAILED|cannot|Missing required|'
                       r'exit code [1-9])\b')
STRIP = '`"\' \t'


AUX = ('placebo', 'pilot')
NOARM = {'blog-search', 'skill-routing'}


def is_aux(r):
    return any(a in (r.get('batch') or '') for a in AUX)


def study_date(s):
    mm = re.search(r'(\d{8})', s or '')
    return mm.group(1) if mm else '0'


def current_images(rows):
    """per-task current task-package image, taken from the qwen axis (run last, images verified)."""
    cur = {}
    for r in rows:
        if r.get('axis') == 'qwen' and r.get('image') and not is_aux(r):
            cur.setdefault(r['task'], set()).add(r['image'])
    return {t: sorted(v)[0] for t, v in cur.items()}


def build_index(rows, principled=True):
    """(axis, task, arm, trial) -> cell path.

    principled=True reproduces the selection used for RQ2: trials r1-r3, no auxiliary batches,
    only cells whose task-package image equals the task's current image, and the latest study
    among the survivors.  principled=False reproduces the earlier behaviour (last manifest row
    wins) so the two can be compared.
    """
    idx = {}
    if not principled:
        for r in rows:
            if r.get('arm') in ('OriginalSkill', 'FixedSkill'):
                idx[(r['axis'], r['task'], r['arm'], r['trial'])] = EXP + r['rel_path'] + '/'
        return idx
    cur = current_images(rows)
    best = {}
    for r in rows:
        k = (r['axis'], r['task'], r['arm'], r['trial'])
        if k[2] not in ('OriginalSkill', 'FixedSkill') or k[3] not in TRIALS:
            continue
        if is_aux(r):
            continue
        if k[1] in NOARM and k[2] == 'NoSkill':
            continue
        cim = cur.get(k[1])
        if cim and r.get('image') != cim:
            continue
        prev = best.get(k)
        if prev is None or study_date(r.get('study')) > study_date(prev.get('study')):
            best[k] = r
    for k, r in best.items():
        idx[k] = EXP + r['rel_path'] + '/'
    return idx


def canon(name: str) -> str:
    n = name.split('::')[-1].split('[')[0]
    for pre in ('test_check_', 'test_', 'check_'):
        if n.startswith(pre):
            return n[len(pre):].strip()
    return n.strip()


def parse(cell: str):
    """-> list of turns: idx, tool, arg, result, is_error, out_tok, in_tok, ts"""
    turns = []
    p = os.path.join(cell, 'cli.stdout.jsonl')
    if not os.path.exists(p):
        return turns
    last = None
    for line in open(p, errors='ignore'):
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get('type')
        if t == 'assistant':
            msg = d.get('message') or {}
            u = msg.get('usage') or {}
            out_tok = u.get('output_tokens') or 0
            in_tok = (u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0) \
                + (u.get('cache_creation_input_tokens') or 0)
            first = True
            for blk in (msg.get('content') or []):
                if isinstance(blk, dict) and blk.get('type') == 'tool_use':
                    turns.append({'idx': len(turns), 'tool': blk.get('name'),
                                  'arg': json.dumps(blk.get('input') or {}, ensure_ascii=False),
                                  'result': '', 'is_error': False,
                                  'out_tok': out_tok if first else 0,
                                  'in_tok': in_tok if first else 0,
                                  'ts': d.get('timestamp')})
                    first = False
            if first and msg.get('content'):   # a text-only assistant message
                turns.append({'idx': len(turns), 'tool': '(text)', 'arg': '',
                              'result': '', 'is_error': False, 'out_tok': out_tok,
                              'in_tok': in_tok, 'ts': d.get('timestamp')})
        elif t == 'user':
            for blk in ((d.get('message') or {}).get('content') or []):
                if isinstance(blk, dict) and blk.get('type') == 'tool_result':
                    c = blk.get('content')
                    if isinstance(c, list):
                        c = ' '.join(str(x.get('text', '')) if isinstance(x, dict) else str(x)
                                     for x in c)
                    c = str(c or '')
                    if turns:
                        turns[-1]['result'] += c
                        turns[-1]['is_error'] = turns[-1]['is_error'] or bool(blk.get('is_error')) \
                            or bool(ERR_WORDS.search(c[:600]))
    return turns


def checks(cell: str):
    p = os.path.join(cell, 'benchflow/verifier/ctrf.json')
    if not os.path.exists(p):
        return set()
    try:
        tests = (json.load(open(p)).get('results') or {}).get('tests') or []
    except Exception:
        return set()
    return {canon(t.get('name', '')) for t in tests if t.get('status') != 'passed'}


def result(cell: str):
    p = os.path.join(cell, 'result.json')
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p))
    except Exception:
        return {}
    return {k: d.get(k) for k in ('score', 'total_tokens', 'api_calls', 'num_turns',
                                  'agent_seconds', 'termination_reason')}


def analyze(cell: str, desc: dict):
    turns = parse(cell)
    ship = [a.strip(STRIP) for a in desc.get('anchors_shipped_only', []) if len(a.strip(STRIP)) >= 5]
    fix = [a.strip(STRIP) for a in desc.get('anchors_fixed_only', []) if len(a.strip(STRIP)) >= 5]
    bases = [os.path.basename(f) for f in desc.get('changed_files', [])]

    def hit(text, anchors):
        return any(a in text for a in anchors)

    reads = [t for t in turns if SKILL_PATH.search(t['arg'])
             or (t['tool'] == 'Skill' and 'skill' in t['arg'].lower())]
    exec_changed = [t for t in turns if any(b and b in t['arg'] for b in bases)]
    ship_agent = sorted({a for a in ship if any(a in t['arg'] for t in turns)})
    ship_out = sorted({a for a in ship if any(a in t['result'] for t in turns)})
    fix_agent = sorted({a for a in fix if any(a in t['arg'] for t in turns)})

    manifest = [t['idx'] for t in turns
                if hit(t['result'], ship) or hit(t['arg'], ship)
                or (t['is_error'] and any(b and b in t['arg'] for b in bases))]
    first_manifest = min(manifest) if manifest else None

    settled = None
    if first_manifest is not None and fix_agent:
        for t in turns:
            if t['idx'] > first_manifest and any(a in t['arg'] for a in fix_agent):
                settled = t['idx']
                break

    # cost of the incident, measured inside this trajectory
    seg_from = first_manifest
    seg_to = settled if settled is not None else len(turns)
    waste_turns = 0
    waste_secs = None
    if seg_from is not None and seg_to > seg_from:
        seg = [t for t in turns if seg_from <= t['idx'] < seg_to]
        waste_turns = len(seg)
        ts = [t['ts'] for t in seg if t['ts']]
        if len(ts) >= 2:
            try:
                import datetime as _dt
                a = _dt.datetime.fromisoformat(ts[0].replace('Z', '+00:00'))
                b = _dt.datetime.fromisoformat(ts[-1].replace('Z', '+00:00'))
                waste_secs = (b - a).total_seconds()
            except Exception:
                waste_secs = None

    rel = {canon(c) for c in (desc.get('related_checks') or [])}
    fails = {c for c in checks(cell) if c in rel}
    return {'cell': cell, 'n_turns': len(turns),
            'skill_read': bool(reads),
            'read_via_path': bool([t for t in reads if SKILL_PATH.search(t['arg'])]),
            'read_via_tool': bool([t for t in reads if t['tool'] == 'Skill']),
            'exec_changed_file': bool(exec_changed),
            'ship_anchor_agent': len(ship_agent), 'ship_anchor_output': len(ship_out),
            'fix_anchor_agent': len(fix_agent),
            'used': bool(exec_changed) or bool(ship_agent),
            'manifested': first_manifest is not None,
            'first_manifest': first_manifest, 'settled': settled,
            'settled_found': settled is not None,
            'waste_turns': waste_turns,
            'waste_turn_share': (waste_turns / len(turns)) if turns else None,
            'waste_secs': waste_secs,
            'related_fails': sorted(fails), 'n_related_fails': len(fails),
            'outcome': result(cell)}


def classify(o: dict, f: dict):
    """two-level: exposure = read the skill; response given exposure."""
    if not o['skill_read']:
        return 'Unused (induced)' if f['skill_read'] else 'Unused (both arms)'
    if not o['used']:
        return 'Bypass'
    if o['n_related_fails'] and f['n_related_fails']:
        return 'BothFail (control)'
    if o['n_related_fails'] and not f['n_related_fails']:
        return 'Follow -> failure'
    if o['manifested'] and f['used']:
        return 'Recover -> success'
    return 'Used, no effect'


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def main() -> int:
    rows = list(csv.DictReader(open(MANIFEST)))
    principled = os.environ.get('WSRAW', '0') != '1'
    idx = build_index(rows, principled=principled)
    print('cell resolution: %s (%d Original/Fixed cells)'
          % ('RQ2 selection rule (image-aligned, latest study)' if principled
             else 'RAW manifest, last row wins', len(idx)))

    out, seen, dropped, skipped_trial = [], set(), [], []
    for (axis, task, arm, trial) in list(idx):
        if trial not in TRIALS:
            skipped_trial.append((task, axis, trial))
            continue
        if (axis, task, trial) in seen:
            continue
        seen.add((axis, task, trial))
        co, cf = idx.get((axis, task, 'OriginalSkill', trial)), idx.get((axis, task, 'FixedSkill', trial))
        dp = os.path.join(DESC, task + '.json')
        if not (co and cf and os.path.exists(dp) and os.path.exists(co + 'result.json')):
            continue
        desc = json.load(open(dp))
        so, sf = analyze(co, desc), analyze(cf, desc)
        if so['n_turns'] == 0 or sf['n_turns'] == 0:
            dropped.append((task, axis, trial, so['n_turns'], sf['n_turns']))
            continue
        resp = classify(so, sf)
        ty = [t.strip() for t in (desc.get('types') or []) if t.strip()] or \
             [desc.get('legacy_type') or '?']
        score_o, score_f = so['outcome'].get('score'), sf['outcome'].get('score')
        out.append({
            'task': task, 'axis': axis, 'trial': trial, 'batch': desc.get('batch'),
            'type_primary': ty[0], 'n_types': len(ty),
            'exposed': so['skill_read'], 'response': resp,
            'read_via_path': so['read_via_path'], 'read_via_tool': so['read_via_tool'],
            'used': so['used'], 'exec_changed_file': so['exec_changed_file'],
            'manifested': so['manifested'],
            'ship_anchor_agent': so['ship_anchor_agent'], 'ship_anchor_output': so['ship_anchor_output'],
            'n_related_fails_original': so['n_related_fails'],
            'n_related_fails_fixed': sf['n_related_fails'],
            'first_manifest_turn': so['first_manifest'], 'settled_turn': so['settled'],
            'settled_found': so['settled_found'],
            'waste_turns': so['waste_turns'], 'waste_turn_share': so['waste_turn_share'],
            'waste_tokens_est': (so['outcome'].get('total_tokens') or 0) * (so['waste_turn_share'] or 0),
            'waste_secs': so['waste_secs'],
            'score_original': score_o, 'score_fixed': score_f,
            'delta_score': (score_f - score_o) if (score_o is not None and score_f is not None) else None,
            'tok_original': so['outcome'].get('total_tokens'),
            'tok_fixed': sf['outcome'].get('total_tokens'),
            'secs_original': so['outcome'].get('agent_seconds'),
            'secs_fixed': sf['outcome'].get('agent_seconds'),
            'turns_original': so['n_turns'], 'turns_fixed': sf['n_turns'],
        })

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'labels_v3.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    # ---------------- sub-RQ tables ----------------
    if skipped_trial:
        import collections as _c
        print('EXCLUDED legacy trials (design is r1-r3):', len(skipped_trial),
              '->', dict(_c.Counter(t for _, _, t in skipped_trial)))
    if dropped:
        print('SKIPPED (empty trajectory in one arm, not a behaviour):')
        for t, a, tr, x, y in dropped:
            print(f'   {t} {a} {tr} turnsO={x} turnsF={y}')
    N = len(out)
    print('=' * 100)
    print('RQ3 AUDIT -- paired cells:', N)
    print('=' * 100)

    print('\n### 3.1 EXPOSURE  (exposure = the agent read the skill)')
    e = sum(1 for r in out if r['exposed'] is True)
    print(f'  exposed  {e}/{N} = {e/N*100:.1f}%    unused {N-e}/{N} = {(N-e)/N*100:.1f}%')
    print(f'  {"axis":<10}{"n":>5}{"exposed":>9}{"rate":>7}{"read_via_Skill_tool":>22}')
    for ax in sorted({r['axis'] for r in out}):
        s = [r for r in out if r['axis'] == ax]
        ex = sum(1 for r in s if r['exposed'] is True)
        via_tool = sum(1 for r in s if r['read_via_tool'] is True)
        print(f'  {ax:<10}{len(s):>5}{ex:>9}{ex/len(s)*100:>6.0f}%{via_tool:>22}')

    print('\n### 3.2 RESPONSE  (given exposure)')
    for k, v in collections.Counter(r['response'] for r in out).most_common():
        print(f'  {v:>4}  {k}')
    order = ['Bypass', 'Follow -> failure', 'Recover -> success',
             'BothFail (control)', 'Used, no effect', 'Unused (induced)', 'Unused (both arms)']
    axes = sorted({r['axis'] for r in out})
    print(f'\n  {"response":<24}' + ''.join(f'{a:>10}' for a in axes))
    for k in order:
        print(f'  {k:<24}' + ''.join(f'{sum(1 for r in out if r["axis"]==a and r["response"]==k):>10}'
                                     for a in axes))

    print('\n### 3.2b RESPONSE x TYPE (n>=6, current taxonomy first)')
    g = collections.defaultdict(collections.Counter)
    gn = collections.Counter()
    for r in out:
        g[r['type_primary']][r['response']] += 1
        gn[r['type_primary']] += 1
    print(f'  {"type":<46}{"n":>5}{"Bypass":>8}{"Follow":>8}{"Recover":>9}{"BothFail":>10}')
    for t in sorted(gn, key=lambda x: -gn[x]):
        if gn[t] < 6:
            continue
        c = g[t]
        print(f'  {t:<46}{gn[t]:>5}{c.get("Bypass",0):>8}{c.get("Follow -> failure",0):>8}'
              f'{c.get("Recover -> success",0):>9}{c.get("BothFail (control)",0):>10}')

    print('\n### 3.3 OUTCOME  (per response class)')
    print(f'  {"response":<24}{"n":>5}{"scoreO":>8}{"scoreF":>8}{"dScore":>8}'
          f'{"dTok/run":>10}{"dSec/run":>10}')
    for k in order:
        s = [r for r in out if r['response'] == k]
        if not s:
            continue
        dt = mean([(r['tok_original'] - r['tok_fixed']) for r in s
                   if r['tok_original'] is not None and r['tok_fixed'] is not None])
        ds = mean([(r['secs_original'] - r['secs_fixed']) for r in s
                   if r['secs_original'] is not None and r['secs_fixed'] is not None])
        print(f'  {k:<24}{len(s):>5}{mean([r["score_original"] for r in s]):>8.3f}'
              f'{mean([r["score_fixed"] for r in s]):>8.3f}{mean([r["delta_score"] for r in s]):>+8.3f}'
              f'{(dt/1000 if dt else 0):>+9.0f}k{(ds if ds else 0):>+10.0f}')

    print('\n### 3.3b INCIDENT COST measured inside the trajectory (the detour)')
    print(f'  {"response":<24}{"n":>5}{"settled":>8}{"detour_turns":>13}{"turn_share":>11}'
          f'{"detour_tok_est":>15}{"detour_secs":>12}')
    for k in order:
        s = [r for r in out if r['response'] == k and r['first_manifest_turn'] is not None]
        if not s:
            continue
        wt = mean([r['waste_turns'] for r in s])
        sh = mean([r['waste_turn_share'] for r in s])
        we = mean([r['waste_tokens_est'] for r in s])
        ws = mean([r['waste_secs'] for r in s])
        sf = sum(1 for r in s if r['settled_found'] is True)
        print(f'  {k:<24}{len(s):>5}{sf:>8}{wt:>13.1f}{(sh or 0)*100:>10.0f}%'
              f'{(we/1000 if we else 0):>14.0f}k{(ws if ws is not None else 0):>12.0f}')

    print('\n### 3.3c Follow -> failure, by model (score lost vs incidents)')
    for ax in axes:
        s = [r for r in out if r['axis'] == ax]
        fw = [r for r in s if r['response'] == 'Follow -> failure']
        rc = [r for r in s if r['response'] == 'Recover -> success']
        by = [r for r in s if r['response'] == 'Bypass']
        print(f'  {ax:<10} Follow={len(fw):<4} Recover={len(rc):<4} Bypass={len(by):<4} '
              f'mean dScore(Follow)={mean([r["delta_score"] for r in fw]) or 0:+.3f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
