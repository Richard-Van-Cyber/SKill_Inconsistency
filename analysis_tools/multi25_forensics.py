#!/usr/bin/env python3
"""Forensics for the multi25 study, run on OUR OWN OriginalSkill traces.

This is step 2 of the repair protocol (P12): before editing any doc text, show that the
inconsistency actually cost something in this study's runs -- not merely that an audit
flagged it.

The decisive test this adds over a plain error count is *doc-induced*:

    a failing command / missing module is only repairable by editing the doc if the
    doc actually mentions it. `python: command not found` is doc-induced when the skill
    text says `python scripts/...`; it is NOT when the agent invented the command.

For every error signature we therefore also report whether the token appears in the
task's skill tree, and in which file(s).

    python3 analysis_tools/multi25_forensics.py --study experiments/multi25-20260925 \
            --arm OriginalSkill [--tasks a,b]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

SIGS = [
    ('cmd_not_found', re.compile(r'(\S+): command not found')),
    ('pep668', re.compile(r'externally-managed-environment')),
    ('no_module', re.compile(r"No module named '([^']+)'")),
    ('eisdir', re.compile(r'EISDIR')),
    ('file_too_big', re.compile(r'exceeds maximum allowed size')),
    ('no_such_file', re.compile(r'No such file or directory')),
    ('permission', re.compile(r'Permission denied')),
    ('timeout', re.compile(r'Command timed out')),
    ('traceback', re.compile(r'Traceback \(most recent call last\)')),
]
# Signatures whose payload names a thing the doc could plausibly have told the agent to use.
DOC_CHECKED = {'cmd_not_found', 'no_module'}


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def find_trace(cell: Path):
    hits = sorted(cell.rglob('cli.stdout.jsonl'))
    return hits[0] if hits else None


def scan(log: Path):
    errs = Counter()
    detail = defaultdict(Counter)
    skills = []
    bash = 0
    with log.open(errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get('type') == 'assistant':
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_use':
                        continue
                    if c.get('name') == 'Skill':
                        skills.append((c.get('input') or {}).get('skill'))
                    elif c.get('name') == 'Bash':
                        bash += 1
            elif o.get('type') == 'user':
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_result':
                        continue
                    txt = text_of(c.get('content'))
                    for name, rx in SIGS:
                        m = rx.search(txt)
                        if m:
                            errs[name] += 1
                            detail[name][(m.group(1) if m.groups() else '')[:40]] += 1
    return errs, detail, skills, bash


def doc_index(task_dir: Path):
    """token -> list of skill files mentioning it (first path component = skill name)."""
    idx = defaultdict(list)
    skills_root = task_dir / 'environment' / 'skills'
    if not skills_root.is_dir():
        return idx
    for p in skills_root.rglob('*'):
        if not p.is_file() or p.suffix not in ('.md', '.py', '.js', '.sh', '.txt', '.json', '.yaml', '.yml'):
            continue
        try:
            txt = p.read_text(errors='replace')
        except Exception:
            continue
        rel = str(p.relative_to(skills_root))
        for tok in set(re.findall(r'[A-Za-z_][A-Za-z0-9_.+-]{1,40}', txt)):
            idx[tok].append(rel)
        idx['__text__:' + rel] = txt
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--study', required=True)
    ap.add_argument('--arm', default='OriginalSkill')
    ap.add_argument('--tasks', default='')
    ap.add_argument('--out', default='/tmp/multi25_forensics.json')
    args = ap.parse_args()
    study = Path(args.study)
    runs = study / 'runs'
    tasks = sorted(p.name for p in (study / 'inputs' / 'selected_tasks').iterdir() if p.is_dir())
    if args.tasks:
        want = {t.strip() for t in args.tasks.split(',')}
        tasks = [t for t in tasks if t in want]

    result = {}
    print(f"{'task':44}{'score':>16}{'calls':>7}{'tok k':>8}{'sec':>6}{'err':>5}"
          f"{'skills':>7}  doc-induced defects")
    print('-' * 140)
    for task in tasks:
        task_dir = study / 'inputs' / 'selected_tasks' / task
        idx = doc_index(task_dir)
        cells = sorted(p for p in runs.glob(f'{task}__{args.arm}__r*') if p.is_dir())
        rows = []
        for cell in cells:
            rj = cell / 'result.json'
            meta = json.loads(rj.read_text()) if rj.exists() else {}
            tr = find_trace(cell)
            if not tr:
                continue
            errs, detail, skills, bash = scan(tr)
            rows.append(dict(cell=cell.name, meta=meta, errs=errs, detail=detail,
                             skills=skills, bash=bash))
        if not rows:
            print(f'{task:44}{"(no traces yet)":>16}')
            continue
        sc = [r['meta'].get('score') for r in rows if r['meta'].get('score') is not None]
        calls = [r['meta'].get('api_calls') for r in rows if r['meta'].get('api_calls')]
        toks = [r['meta'].get('total_tokens') for r in rows if r['meta'].get('total_tokens')]
        secs = [r['meta'].get('agent_seconds') for r in rows if r['meta'].get('agent_seconds')]
        sig = Counter()
        det = defaultdict(Counter)
        for r in rows:
            sig.update(r['errs'])
            for k, v in r['detail'].items():
                det[k].update(v)
        nerr = sum(sig.values())
        sk = statistics.mean([len(r['skills']) for r in rows])

        # doc-induced: does the payload name appear anywhere in the skill tree?
        induced = {}
        for name in DOC_CHECKED:
            for payload, n in det[name].items():
                if not payload:
                    continue
                hits = sorted({f.split('/')[0] for f in idx.get(payload, [])})
                induced[f'{name}:{payload}'] = dict(n=n, in_doc=hits)

        result[task] = dict(
            rows=[dict(cell=r['cell'], status=r['meta'].get('status'), score=r['meta'].get('score'),
                       api_calls=r['meta'].get('api_calls'), total_tokens=r['meta'].get('total_tokens'),
                       agent_seconds=r['meta'].get('agent_seconds'),
                       budget_stop_reason=r['meta'].get('budget_stop_reason'),
                       skills=r['skills'], bash=r['bash'], errors=dict(r['errs']))
                  for r in rows],
            summary=dict(score_mean=statistics.mean(sc) if sc else None, n=len(rows),
                         calls_med=statistics.median(calls) if calls else None,
                         tok_med=statistics.median(toks) if toks else None,
                         sec_med=statistics.median(secs) if secs else None,
                         skills_mean=sk, errors=dict(sig)),
            doc_induced=induced)

        sc_s = ','.join('-' if r['meta'].get('score') is None else f"{r['meta']['score']:.2f}" for r in rows)
        print(f"{task:44}{sc_s:>16}{(statistics.median(calls) if calls else 0):>7.0f}"
              f"{(statistics.median(toks)/1000 if toks else 0):>8.0f}"
              f"{(statistics.median(secs) if secs else 0):>6.0f}{nerr:>5}{sk:>7.1f}  "
              f"{ {k: v for k, v in induced.items()} }")

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f'\n[written] {args.out}')


if __name__ == '__main__':
    main()
