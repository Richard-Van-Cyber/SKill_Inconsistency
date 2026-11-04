#!/usr/bin/env python3
"""RQ3 instrument: behavioural diff between the Original and Fixed trajectories of one (task, model).

Emits, for each arm:
  * outcome: score, tokens, calls, turns, seconds, truncation
  * an ordered event list: turn, tool, compact argument, and whether the tool result was an error
  * domain signals: skill files read, error signatures, files written
and then the set difference — the behaviour present in Original but not in Fixed.  The paired
contrast is what licenses attribution to the inconsistency: behaviour that is identical in both arms
cannot be caused by it.

Usage: traj_diff.py <experiments_dir> <task> <model: haiku|deepseek|qwen> [trial]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

EXP = sys.argv[1]
TASK = sys.argv[2]
MODEL = sys.argv[3] if len(sys.argv) > 3 else 'haiku'
TRIAL = sys.argv[4] if len(sys.argv) > 4 else 'r1'

STUDY_GLOB = {
    'haiku': ['wildskills25-20261001a', 'wildskills25-20261001b', 'wildskills25-20261001c',
              'wildskills12-realign-20261001', 'wildskills-realign-haiku-20261001',
              'wildskills-gapfix-haiku-20261001', 'wildskills13-20260929'],
    'deepseek': ['wildskills25-deepseek-20261001', 'wildskills13-deepseek-20260929',
                 'wildskills-realign-deepseek-20261001'],
    'qwen': ['wildskills25-ollama-20260930', 'wildskills13-ollama-20260930',
             'wildskills12-ollama-20260930'],
}[MODEL]

ERR_MARK = re.compile(r'\b(error|Error|ERROR|Traceback|No such file|not found|command not found|'
                      r'unrecognized|unexpected|invalid|failed|FAILED|cannot|'
                      r'Missing required|exit code [1-9])\b')


def find_cell(arm: str):
    for study in STUDY_GLOB:
        pat = f'{EXP}/{study}/runs/{TASK}__{arm}__{TRIAL}/*/'
        hits = glob.glob(pat)
        if hits:
            return study, hits[0]
    return None, None


def compact(name: str, inp: dict) -> str:
    if name == 'Bash':
        return (inp.get('command') or '')[:110].replace('\n', ' ; ')
    if name in ('Read', 'Write', 'Edit', 'Glob', 'Grep', 'NotebookEdit'):
        v = inp.get('file_path') or inp.get('pattern') or inp.get('path') or ''
        return str(v)[:110]
    return json.dumps(inp, ensure_ascii=False)[:90]


def parse(path: str):
    events, skill_reads, errors, writes = [], set(), [], set()
    for line in open(path, errors='ignore'):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get('type') not in ('assistant', 'user'):
            continue
        msg = d.get('message') or {}
        for blk in (msg.get('content') or []):
            if not isinstance(blk, dict):
                continue
            if blk.get('type') == 'tool_use':
                arg = compact(blk.get('name', '?'), blk.get('input') or {})
                events.append({'tool': blk.get('name'), 'arg': arg, 'err': False})
                a = arg.lower()
                if '/skills/' in a or a.startswith('skills/') or 'skill.md' in a:
                    skill_reads.add(arg[:90])
                if blk.get('name') in ('Write', 'Edit'):
                    writes.add(arg[:90])
            elif blk.get('type') == 'tool_result':
                text = blk.get('content')
                if isinstance(text, list):
                    text = ' '.join(str(c.get('text', '')) if isinstance(c, dict) else str(c)
                                    for c in text)
                text = str(text or '')
                is_err = bool(blk.get('is_error')) or bool(ERR_MARK.search(text[:400]))
                if events:
                    events[-1]['err'] = events[-1]['err'] or is_err
                if is_err:
                    errors.append((len(events), text.strip().replace('\n', ' ')[:150]))
    return events, skill_reads, errors, writes


def outcome(cell: str):
    rp = glob.glob(cell + 'result.json')
    if not rp:
        return {}
    d = json.load(open(rp[0]))
    return {k: d.get(k) for k in ('status', 'score', 'total_tokens', 'api_calls', 'num_turns',
                                  'agent_seconds', 'termination_reason')}


def report(arm: str):
    study, cell = find_cell(arm)
    if not cell:
        print(f'  [{arm}] no cell found ({TASK} {TRIAL})')
        return None
    o = outcome(cell)
    ev, sk, er, wr = parse(cell + 'cli.stdout.jsonl')
    print(f'  [{arm}] {study}/{TASK}__{arm}__{TRIAL}')
    print(f'      score={o.get("score")} tokens={o.get("total_tokens")} calls={o.get("api_calls")} '
          f'turns={o.get("num_turns")} secs={o.get("agent_seconds")} stop={o.get("termination_reason")}')
    print(f'      tool events={len(ev)}  skill-file reads={len(sk)}  error results={len(er)}  writes={len(wr)}')
    if sk:
        print(f'      skill reads: ' + '; '.join(sorted(sk)[:3]))
    print(f'      sequence: ' + ' -> '.join(f'{e["tool"]}{"!" if e["err"] else ""}' for e in ev[:26]) +
          (' ...' if len(ev) > 26 else ''))
    for turn, txt in er[:4]:
        print(f'      error@turn{turn}: {txt}')
    return {'outcome': o, 'events': ev, 'skill': sk, 'errors': er, 'writes': wr, 'cell': cell}


print(f'=== {TASK} / {MODEL} / {TRIAL}')
a = report('OriginalSkill')
b = report('FixedSkill')
if a and b:
    def keyset(r):
        return {(e['tool'], e['arg'][:60]) for e in r['events']}
    only_orig = keyset(a) - keyset(b)
    only_fixed = keyset(b) - keyset(a)
    print(f'  --- paired contrast')
    print(f'      errors Original={len(a["errors"])} Fixed={len(b["errors"])}')
    print(f'      behaviour only in Original ({len(only_orig)}): ' +
          '; '.join(f'{t}:{x[:60]}' for t, x in list(only_orig)[:5]))
    print(f'      behaviour only in Fixed ({len(only_fixed)}): ' +
          '; '.join(f'{t}:{x[:60]}' for t, x in list(only_fixed)[:5]))
    oa, ob = a['outcome'], b['outcome']
    if oa.get('score') is not None and ob.get('score') is not None:
        print(f'      delta score={ob["score"] - oa["score"]:+.3f} '
              f'tokens={(ob.get("total_tokens") or 0) - (oa.get("total_tokens") or 0):+,} '
              f'secs={(ob.get("agent_seconds") or 0) - (oa.get("agent_seconds") or 0):+.0f}')
