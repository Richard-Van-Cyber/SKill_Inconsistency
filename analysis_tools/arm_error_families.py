#!/usr/bin/env python3
"""Per-arm error-family comparison over the 10 DRS tasks.

Attribution logic: an error family that the NoSkill arm does not hit but the
skill arms do is *skill-induced*. That is the evidence required before repairing
any doc text.
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter, defaultdict

RUNS = 'haiku45-threeway-20260917/runs'
TASKS = ['civ6-adjacency-optimizer', 'court-form-filling',
         'crystallographic-wyckoff-position-analysis', 'data-to-d3', 'dialogue-parser',
         'energy-market-pricing', 'fix-druid-loophole-cve', 'fix-erlang-ssh-cve',
         'grid-dispatch-operator', 'mario-coin-counting']
ARMS = ['NoSkill', 'OriginalSkill', 'RepairedSkill']

FAMILIES = [
    ('cmd_not_found', re.compile(r'(\S+): command not found')),
    ('pep668', re.compile(r'externally-managed-environment')),
    ('no_module', re.compile(r"No module named '([^']+)'")),
    ('eisdir', re.compile(r'EISDIR')),
    ('file_too_big', re.compile(r'exceeds maximum allowed size')),
    ('no_such_file', re.compile(r'No such file or directory')),
    ('pip_thrash', re.compile(r'(pip3? install|--break-system-packages)')),
    ('timeout', re.compile(r'Command timed out')),
    ('traceback', re.compile(r'Traceback \(most recent call last\)')),
    ('rg_bad_type', re.compile(r'unrecognized file type')),
]


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def scan(log):
    """Return Counter of family->n and detail Counter for sub-captures."""
    cnt, detail = Counter(), defaultdict(Counter)
    bash_cmds = []
    with open(log, errors='replace') as fh:
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
                    if isinstance(c, dict) and c.get('type') == 'tool_use' \
                            and c.get('name') == 'Bash':
                        bash_cmds.append(str((c.get('input') or {}).get('command') or ''))
            elif o.get('type') == 'user':
                for c in (o.get('message') or {}).get('content') or []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_result':
                        continue
                    txt = text_of(c.get('content'))
                    if not txt:
                        continue
                    for fam, rx in FAMILIES:
                        m = rx.search(txt)
                        if m:
                            cnt[fam] += 1
                            detail[fam][(m.group(1) if m.groups() else '')[:40]] += 1
    # pip thrash is better measured from the commands the agent issued
    pip_cmds = [c for c in bash_cmds if re.search(r'\bpip3? install', c)]
    cnt['pip_cmds'] = len(pip_cmds)
    detail['pip_cmds'][''] = len(pip_cmds)
    return cnt, detail


def main():
    table = defaultdict(lambda: defaultdict(Counter))   # task -> arm -> fam
    detail = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    for task in TASKS:
        for arm in ARMS:
            for d in sorted(glob.glob(f'{RUNS}/{task}__{arm}__r*')):
                logs = glob.glob(f'{d}/**/cli.stdout.jsonl', recursive=True)
                if not logs:
                    continue
                cnt, det = scan(logs[0])
                for k, v in cnt.items():
                    table[task][arm][k] += v
                for fam, c in det.items():
                    detail[task][arm][fam].update(c)

    json.dump({t: {a: dict(c) for a, c in v.items()} for t, v in table.items()},
              open('/tmp/arm_error_families.json', 'w'), indent=1)

    print(f"{'task':38}{'arm':14}{'cmdNF':>6}{'pep668':>7}{'noMod':>6}{'pipCmd':>7}"
          f"{'big':>5}{'nosuch':>7}{'TO':>4}{'trace':>6}")
    print('-' * 104)
    for task in TASKS:
        for arm in ARMS:
            c = table[task][arm]
            print(f"{task:38}{arm:14}{c['cmd_not_found']:6}{c['pep668']:7}"
                  f"{c['no_module']:6}{c['pip_cmds']:7}{c['file_too_big']:5}"
                  f"{c['no_such_file']:7}{c['timeout']:4}{c['traceback']:6}")
        print()

    print("=== which commands were 'not found' / which modules missing ===")
    for task in TASKS:
        for arm in ARMS:
            d = detail[task][arm]
            if d['cmd_not_found'] or d['no_module']:
                print(f"  {task:38}{arm:14} cmd={dict(d['cmd_not_found'])} "
                      f"mod={dict(d['no_module'])}")


if __name__ == '__main__':
    main()
