#!/usr/bin/env python3
"""Evidence pass over the ORIGINALSkill traces of the 10 DRS tasks.

Goal (from the repair brief): before writing any repair, find out which audited
inconsistencies actually cost something in the original runs -- a direct failure,
extra tokens, or extra wall-clock.

For every OriginalSkill cell (the 2026-09-17 three-way study, identical config to
the DRS arm) this records:
  * errors, their signature, and the turn they happened on
  * which skills were loaded (the `Skill` tool) and which skill files were touched
  * tokens / calls / seconds
  * whether an error text matches an identifier that appears verbatim in one of
    the task's audit findings (a candidate attribution)

Output: /tmp/drs_original_audit.json + a printed per-task digest.
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
from collections import Counter, defaultdict

RUNS = 'haiku45-threeway-20260917/runs'
TASKS = ['civ6-adjacency-optimizer', 'court-form-filling',
         'crystallographic-wyckoff-position-analysis', 'data-to-d3', 'dialogue-parser',
         'energy-market-pricing', 'fix-druid-loophole-cve', 'fix-erlang-ssh-cve',
         'grid-dispatch-operator', 'mario-coin-counting']

ID_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]{5,}')
GENERIC = set("""python command directory analysis query apache operation frames frame
scale shape columns column append start policy downtime baseline solution goals goal
lists list problem domain object output input value error path file data result
machine job jobs task tasks time index name names type types number count check run
script code line test tests api request response suricata state model section""".split())
SPECIFIC_EXTRA = {'markdown', 'worker', 'timeout', 'matplotlib', 'numpy', 'scipy',
                  'pandas', 'cvxpy', 'clairvoyant'}


def is_specific(tok):
    t = tok.lower()
    if t in GENERIC:
        return False
    if t in SPECIFIC_EXTRA:
        return True
    return len(tok) >= 6 and ('_' in tok or any(c.isupper() for c in tok[1:]))


def finding_keywords(task):
    p = f'tasks/{task}/audit_report.json'
    rep = json.load(open(p)) if os.path.exists(p) else {}
    out = {}
    for f in rep.get('findings') or []:
        ev = f.get('evidence') or {}
        ids, files = set(), []
        for k in ('source_a', 'source_b'):
            span = (ev.get(k) or {}).get('span_text') or ''
            fp = (ev.get(k) or {}).get('file') or ''
            ids |= {x for x in ID_RE.findall(span) if is_specific(x)}
            if fp and not fp.startswith('<'):
                files.append(fp)
        out[f['id']] = dict(ids=ids, files=files,
                            skill_dirs=sorted({x.split('/')[0] for x in files}),
                            sev=f.get('severity'),
                            impact=(f.get('agent_impact') or {}).get('impact_class'))
    return out


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def scan(log, kw):
    turn = 0
    errors, loaded, read_skill, bash_skill = [], Counter(), 0, 0
    with open(log, errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get('type')
            if t == 'assistant':
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_use':
                        continue
                    turn += 1
                    nm, inp = c.get('name'), c.get('input') or {}
                    if nm == 'Skill':
                        loaded[(inp.get('skill') or '?')] += 1
                    elif nm in ('Read', 'NotebookRead'):
                        if 'skill' in str(inp.get('file_path') or '').lower():
                            read_skill += 1
                    elif nm == 'Bash':
                        if '/skills/' in str(inp.get('command') or ''):
                            bash_skill += 1
            elif t == 'user':
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_result':
                        continue
                    txt = text_of(c.get('content'))
                    if not (c.get('is_error') or 'Traceback' in txt[:400]
                            or txt.startswith('Exit code 1')):
                        continue
                    sig = next((l.strip() for l in txt.splitlines()
                                if any(m in l for m in (
                                    'Error', 'error', 'Traceback', 'FAILED', 'not found',
                                    'command not found', 'No such file'))), txt[:120])
                    errors.append(dict(turn=turn, sig=re.sub(r'\d+', '#', sig)[:160],
                                       raw=txt[:600]))
    return turn, errors, loaded, read_skill, bash_skill


def main():
    per_task = {}
    for task in TASKS:
        kw = finding_keywords(task)
        cells = []
        for d in sorted(glob.glob(f'{RUNS}/{task}__OriginalSkill__r*')):
            logs = glob.glob(f'{d}/**/cli.stdout.jsonl', recursive=True)
            res = json.load(open(f'{d}/result.json'))
            if not logs:
                cells.append(dict(run=os.path.basename(d), no_log=True,
                                  score=res.get('score'), tok=res.get('total_tokens'),
                                  calls=res.get('api_calls'), secs=res.get('agent_seconds')))
                continue
            turn, errors, loaded, rs, bs = scan(logs[0], kw)
            hit = Counter()
            ev = []
            for e in errors:
                ids = {x for x in ID_RE.findall(e['raw']) if is_specific(x)}
                for fid, meta in kw.items():
                    inter = ids & meta['ids']
                    if inter:
                        hit[fid] += 1
                        ev.append(dict(turn=e['turn'], fid=fid, matched=sorted(inter)[:4],
                                       sig=e['sig']))
            cells.append(dict(run=os.path.basename(d), turns=turn, score=res.get('score'),
                              tok=res.get('total_tokens'), calls=res.get('api_calls'),
                              secs=res.get('agent_seconds'),
                              loaded=dict(loaded), read_skill=rs, bash_skill=bs,
                              errors=[e['sig'] for e in errors],
                              matched=dict(hit), evidence=ev[:8]))
        per_task[task] = cells

    json.dump(per_task, open('/tmp/drs_original_audit.json', 'w'), ensure_ascii=False, indent=1)

    print(f"{'task':40}{'score':>15}{'calls':>7}{'tok k':>8}{'sec':>6}{'err':>5}"
          f"{'skillLoad':>10}  top error signatures")
    print('-' * 140)
    for task in TASKS:
        cells = per_task[task]
        sc = [c['score'] for c in cells if c.get('score') is not None]
        ca = [c['calls'] for c in cells if c.get('calls')]
        tk = [c['tok'] for c in cells if c.get('tok')]
        se = [c['secs'] for c in cells if c.get('secs')]
        errs = Counter(e for c in cells for e in c.get('errors', []))
        nl = sum(sum(c.get('loaded', {}).values()) for c in cells)
        print(f"{task:40}{str([round(x,3) for x in sc]):>15}"
              f"{(statistics.median(ca) if ca else 0):7.0f}"
              f"{(statistics.median(tk)/1000 if tk else 0):8.0f}"
              f"{(statistics.median(se) if se else 0):6.0f}"
              f"{sum(len(c.get('errors',[])) for c in cells):5}{nl:10}"
              f"  {list(errs.most_common(2))}")
    print()
    print("=== findings whose identifiers appear in an error text ===")
    for task in TASKS:
        hits = Counter()
        for c in per_task[task]:
            for k, v in (c.get('matched') or {}).items():
                hits[k] += v
        if hits:
            print(f"  {task:40} {dict(hits)}")


if __name__ == '__main__':
    main()
