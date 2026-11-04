#!/usr/bin/env python3
"""LLM cross-validation of the deterministic trajectory coder (RQ3, option C).

For a stratified sample of paired cells, an independent LLM reads a *condensed* view of the
OriginalSkill trajectory and labels the agent's response; the labels are then compared against the
deterministic coder's labels to compute inter-method agreement (raw agreement + Cohen's kappa).

Two backends, auto-selected:
  * DeepSeek (OpenAI-compatible) -- set DEEPSEEK_API_KEY
  * Ollama (local)               -- set OLLAMA_HOST (default http://localhost:11434)

Run:
  DEEPSEEK_API_KEY=... python3 llm_validate.py --n 36 --seed 42
  DEEPSEEK_API_KEY=... python3 llm_validate.py --dry-run   # print prompts, no LLM call
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_v3 as A  # reuse parse(), manifest resolution, descriptor loading

OUT = os.environ.get('WSOUT', '/home/user/project/RQ3/analysis')

# deterministic coder label -> canonical 6-class
DET2CAN = {
    'Follow -> failure': 'follow',
    'Recover -> success': 'recover',
    'Bypass': 'bypass',
    'BothFail (control)': 'bothfail',
    'Used, no effect': 'noeffect',
}
CANONICAL = ['follow', 'recover', 'bypass', 'bothfail', 'noeffect', 'unused']


def det_to_canon(r: dict) -> str:
    r = r['response']
    if r.startswith('Unused'):
        return 'unused'
    return DET2CAN.get(r, 'noeffect')


def sample_cells(rows, n=36, seed=42):
    """stratified by deterministic response class, proportional-ish, reproducible."""
    rng = random.Random(seed)
    by = {}
    for r in rows:
        by.setdefault(det_to_canon(r), []).append(r)
    # ensure each class sampled; weight by sqrt(class size) to avoid tiny-class starvation
    picked = []
    while len(picked) < n and any(by.values()):
        for c in CANONICAL:
            if len(picked) >= n:
                break
            pool = by.get(c, [])
            if pool:
                picked.append(pool.pop(rng.randrange(len(pool))))
    return picked


def compact_trajectory(cell: str, max_turns=40, arg_len=120, res_len=180) -> str:
    """turn i: [tool] arg...  ->  (error?) result..."""
    turns = A.parse(cell)
    lines = []
    for t in turns[:max_turns]:
        a = re.sub(r'\s+', ' ', t['arg'])[:arg_len]
        r = re.sub(r'\s+', ' ', t['result'])[:res_len]
        err = ' [ERROR]' if t['is_error'] else ''
        lines.append(f"{t['idx']}: {t['tool']} {a} -> {err} {r}".strip())
    return '\n'.join(lines)


def describe_inconsistency(desc: dict) -> str:
    """doc claims X vs code does Y, from the fix diff + anchors."""
    ship = desc.get('anchors_shipped_only', [])[:4]
    fix = desc.get('anchors_fixed_only', [])[:4]
    changed = [os.path.basename(f) for f in desc.get('changed_files', [])]
    parts = [f"changed files: {', '.join(changed)}"]
    if ship:
        parts.append("tokens in the shipped (wrong) skill: " + ', '.join(f'`{a}`' for a in ship))
    if fix:
        parts.append("tokens in the fixed (correct) skill: " + ', '.join(f'`{a}`' for a in fix))
    # first removed/added lines from the diff give the doc-vs-code contrast
    for f, v in (desc.get('diff') or {}).items():
        rem = [l.strip() for l in (v.get('removed') or []) if l.strip()][:1]
        add = [l.strip() for l in (v.get('added') or []) if l.strip()][:1]
        if rem or add:
            parts.append(f"in {os.path.basename(f)}: shipped had {rem} ; fixed has {add}")
            break
    return '; '.join(parts)


PROMPT = """You are labeling an agent's execution trace for a study of how *inconsistencies* inside AI
"skills" (documentation + code packages that guide agents) affect agent behavior.

The skill under test contains this inconsistency: {inconsistency}

Here is a condensed trace of what the agent did (each line is one tool action followed by its output):
{trace}

Answer as JSON only, with these keys:
  "read_skill": true/false -- did the agent read or open the skill (its SKILL.md or scripts)?
  "used_inconsistent": true/false -- did the agent actually use the inconsistent element, i.e. run the
      changed script or reproduce the documented-but-wrong behavior?
  "response": one of
      "follow"   (used the wrong behavior and delivered it),
      "recover"  (used it, it went wrong, but corrected before finishing),
      "bypass"   (read the skill but avoided the inconsistent element),
      "bothfail" (the deliverable is wrong regardless of the inconsistency),
      "noeffect" (used it but nothing went wrong),
      "unused"   (never read the skill)
  "reason": one sentence explaining the label.

Output only: {{"read_skill": bool, "used_inconsistent": bool, "response": "...", "reason": "..."}}"""


def call_llm(prompt: str, model=None):
    key = os.environ.get('DEEPSEEK_API_KEY')
    if key:
        model = model or 'deepseek-chat'
        body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                           'temperature': 0, 'max_tokens': 300})
        req = urllib.request.Request('https://api.deepseek.com/chat/completions', data=body.encode(),
                                     headers={'Content-Type': 'application/json',
                                              'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        return d['choices'][0]['message']['content']
    host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    model = model or os.environ.get('OLLAMA_MODEL', 'qwen3.6-35b')
    body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                       'stream': False, 'options': {'temperature': 0}})
    req = urllib.request.Request(host + '/api/chat', data=body.encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
    return d['message']['content']


def parse_answer(text: str) -> str:
    m = re.search(r'\{.*\}', text, re.S)
    try:
        d = json.loads(m.group(0))
    except Exception:
        return 'unparseable'
    resp = str(d.get('response', '')).lower().strip()
    for c in CANONICAL:
        if c in resp:
            return c
    return 'unparseable'


def cohens_kappa(conf):
    """conf: dict[(a,b)] -> count over canonical labels."""
    labels = sorted({k for pair in conf for k in pair})
    n = sum(conf.values())
    po = sum(conf[(c, c)] for c in labels if (c, c) in conf) / n
    pe = 0.0
    for c in labels:
        r = sum(conf[(c, j)] for j in labels if (c, j) in conf)
        cj = sum(conf[(i, c)] for i in labels if (i, c) in conf)
        pe += (r / n) * (cj / n)
    return (po - pe) / (1 - pe) if pe < 1 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=36)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--model', default=None)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(OUT + '/labels_v3.csv')))
    idx = A.build_index(list(csv.DictReader(open(A.MANIFEST))), principled=True)
    cells = sample_cells(rows, a.n, a.seed)
    print(f'sampled {len(cells)} cells (seed={a.seed})')

    conf = {}
    agree = 0
    for i, r in enumerate(cells):
        co = idx.get((r['axis'], r['task'], 'OriginalSkill', r['trial']))
        dp = os.path.join(A.DESC, r['task'] + '.json')
        if not (co and os.path.exists(dp)):
            print(f'  skip {r["task"]} {r["axis"]} {r["trial"]}: no trajectory/descriptor')
            continue
        desc = json.load(open(dp))
        prompt = PROMPT.format(inconsistency=describe_inconsistency(desc),
                               trace=compact_trajectory(co))
        det = det_to_canon(r)
        if a.dry_run:
            print(f'\n=== [{i+1}] {r["task"]} / {r["axis"]} / {r["trial"]}  (det={det})')
            print(prompt[:1200] + ('...' if len(prompt) > 1200 else ''))
            continue
        try:
            text = call_llm(prompt, a.model)
            llm = parse_answer(text)
        except Exception as e:
            print(f'  LLM error on {r["task"]} {r["axis"]} {r["trial"]}: {e}')
            continue
        conf[(det, llm)] = conf.get((det, llm), 0) + 1
        agree += (det == llm)
        print(f'  [{i+1:2d}] {r["task"][:26]:<26} {r["axis"]:<8} det={det:<9} llm={llm:<9} '
              f'{"OK" if det == llm else "DIFF"}')

    if a.dry_run:
        print('\n(dry run: no LLM calls made; inspect the prompts above)')
        return 0

    n = sum(conf.values())
    print(f'\nagreement = {agree}/{n} = {100*agree/n:.0f}%   Cohen kappa = {cohens_kappa(conf):.3f}')
    print('\nconfusion matrix (rows=deterministic, cols=LLM):')
    print('        ' + '  '.join(f'{c[:8]:>8}' for c in CANONICAL))
    for a_ in CANONICAL:
        print(f'{a_:<8}' + '  '.join(f'{conf.get((a_, b), 0):>8}' for b in CANONICAL))
    json.dump({'confusion': {f'{k[0]}|{k[1]}': v for k, v in conf.items()},
               'agreement': agree / n if n else 0,
               'kappa': cohens_kappa(conf)},
              open(OUT + '/llm_validation.json', 'w'), indent=1)
    print('\nsaved', OUT + '/llm_validation.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
