#!/usr/bin/env python3
"""Mine the SkillsBench paper-v1 (claude-code-with-skills) trajectories for the signals
that tell us whether a skill inconsistency was a BINDING constraint in real execution.

Why this dataset: it is the *with-skills* arm, same model family
(claude-haiku-4-5-20251001), and each Skill invocation injects the full SKILL.md into the
transcript -- so we can (a) see the skill text the agent actually read and (b) see whether
the agent then hit an error that the text set it up for.

Per trajectory we record:
  reward, agent_execution seconds, total tokens (summed from per-message usage),
  tool-call counts, which skills were loaded, and every is_error tool result with a
  normalised signature.

Outputs JSON + a per-task digest. Deliberately does NOT judge attribution -- that is a
reading step -- it only measures.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

SIGS = [
    ('cmd_not_found', re.compile(r'(\S+): command not found')),
    ('pep668', re.compile(r'externally-managed-environment')),
    ('no_module', re.compile(r"No module named '([^']+)'")),
    ('importerror', re.compile(r'ImportError|ModuleNotFoundError')),
    ('eisdir', re.compile(r'EISDIR')),
    ('file_too_big', re.compile(r'exceeds maximum allowed size|File content .* exceeds')),
    ('no_such_file', re.compile(r'No such file or directory')),
    ('permission', re.compile(r'Permission denied')),
    ('timeout', re.compile(r'Command timed out|timed out after')),
    ('traceback', re.compile(r'Traceback \(most recent call last\)')),
    ('syntax_error', re.compile(r'SyntaxError')),
    ('key_error', re.compile(r'KeyError')),
    ('value_error', re.compile(r'ValueError')),
    ('type_error', re.compile(r'TypeError')),
    ('attr_error', re.compile(r'AttributeError')),
    ('file_exists', re.compile(r'FileExistsError')),
    ('json_decode', re.compile(r'JSONDecodeError')),
    ('rg_bad_type', re.compile(r'unrecognized file type')),
    ('connection', re.compile(r'Connection refused|Could not resolve host|Temporary failure in name resolution')),
    ('osmismatch', re.compile(r'[Oo]ut of memory|Killed')),
]


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def scan(path: Path):
    rec = dict(errors=Counter(), detail=defaultdict(Counter), skills=[],
               tool_use=0, bash=0, tokens=0, assistant_msgs=0, user_msgs=0,
               err_results=0, err_confirmed=0)
    with path.open(errors='replace') as fh:
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
                rec['assistant_msgs'] += 1
                u = (o.get('message') or {}).get('usage') or {}
                rec['tokens'] += sum(u.get(k) or 0 for k in
                                     ('input_tokens', 'output_tokens',
                                      'cache_read_input_tokens', 'cache_creation_input_tokens'))
                for c in (o.get('message') or {}).get('content') or []:
                    if isinstance(c, dict) and c.get('type') == 'tool_use':
                        rec['tool_use'] += 1
                        if c.get('name') == 'Bash':
                            rec['bash'] += 1
                        elif c.get('name') == 'Skill':
                            rec['skills'].append((c.get('input') or {}).get('skill'))
            elif t == 'user':
                rec['user_msgs'] += 1
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_result':
                        continue
                    txt = text_of(c.get('content'))
                    is_err = c.get('is_error') or bool((o.get('tool_use_result') or {}) and
                                                       o['tool_use_result'] not in (None, '', {}) and
                                                       isinstance(o['tool_use_result'], str))
                    if c.get('is_error'):
                        rec['err_confirmed'] += 1
                    if not (c.get('is_error') or 'Exit code 1' in txt[:200] or 'Error' in txt[:200]):
                        continue
                    rec['err_results'] += 1
                    for name, rx in SIGS:
                        m = rx.search(txt)
                        if m:
                            rec['errors'][name] += 1
                            rec['detail'][name][(m.group(1) if m.groups() else '')[:36]] += 1
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', help='the <date>__paper-v1-... directory')
    ap.add_argument('--out', default='/tmp/skillsbench_traj_mining.json')
    args = ap.parse_args()
    root = Path(args.root)
    per_task = defaultdict(list)
    n = 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        task = d.name.split('__paper-v1')[0]
        rj = d / 'result.json'
        trs = list(d.rglob('claude-code.txt'))
        if not trs:
            continue
        meta = json.loads(rj.read_text()) if rj.exists() else {}
        rec = scan(trs[0])
        rec.update(task=task, trial=d.name, reward=(meta.get('rewards') or {}).get('reward'),
                   agent_sec=(meta.get('timing') or {}).get('agent_execution'),
                   verifier_sec=(meta.get('timing') or {}).get('verifier'),
                   verifier_error=meta.get('verifier_error'), error=meta.get('error'))
        rec['errors'] = dict(rec['errors'])
        rec['detail'] = {k: dict(v) for k, v in rec['detail'].items()}
        per_task[task].append(rec)
        n += 1
    Path(args.out).write_text(json.dumps(per_task, ensure_ascii=False, indent=1))
    print(f'scanned {n} trajectories across {len(per_task)} tasks -> {args.out}')

    print(f"\n{'task':44}{'rew(mean)':>10}{'n':>3}{'agent_s':>9}{'tokens k':>10}"
          f"{'skills':>7}{'errRes':>7}{'cmdNF':>6}  top signatures")
    print('-' * 132)
    for task, rows in sorted(per_task.items()):
        rw = [r['reward'] for r in rows if r.get('reward') is not None]
        sec = [r['agent_sec'] for r in rows if r.get('agent_sec') is not None]
        tok = [r['tokens'] for r in rows if r.get('tokens')]
        sigs = Counter()
        for r in rows:
            sigs.update(r['errors'])
        sk = statistics.mean([len(r['skills']) for r in rows]) if rows else 0
        er = sum(r['err_results'] for r in rows)
        print(f"{task:44}{(statistics.mean(rw) if rw else float('nan')):>10.3f}{len(rows):>3}"
              f"{(statistics.median(sec) if sec else 0):>9.0f}"
              f"{(statistics.median(tok)/1000 if tok else 0):>10.0f}{sk:>7.1f}{er:>7}"
              f"{sigs.get('cmd_not_found',0):>6}  {list(sigs.most_common(3))}")


if __name__ == '__main__':
    main()
