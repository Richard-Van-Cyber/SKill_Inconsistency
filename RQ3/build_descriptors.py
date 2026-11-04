#!/usr/bin/env python3
"""RQ3 step 1 — build one inconsistency descriptor per task.

For every task we diff the shipped skill (``tasks/<t>/environment/skills``) against the repaired one
(``fixed_skills/<t>/environment/skills``) and extract what a trajectory detector needs:

  * which files the repair touched and the exact removed / added lines,
  * *anchors*: distinctive tokens that occur only in the shipped version (the inconsistent signal a
    following agent would reproduce) and only in the repaired version (the corrected signal),
  * the verifier checks whose name or body mentions an anchor, i.e. the checks that should fail when
    the agent follows the inconsistency,
  * the taxonomy class(es) recorded for the task.

Output: RQ3/descriptors/<task>.json and RQ3/descriptors.csv

Usage: build_descriptors.py <repo_root> [out_dir]
"""
from __future__ import annotations

import csv
import difflib
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else REPO / 'RQ3' / 'descriptors')
REGISTRY = REPO / 'experiments' / 'wildskills25-20261001' / 'tasks.json'   # batch25 (23 tasks)
REGISTRY_B13 = REPO / 'experiments' / 'wildskills13-20260929' / 'tasks.json'  # batch13 (14 tasks)
REGISTRY_B12 = REPO / 'experiments' / 'inconsistency-registry.json'          # batch12 (12 tasks, earlier vocabulary)
TASKS = REPO / 'wildskills' / 'dynamic_eval' / 'tasks'
FIXED = REPO / 'wildskills' / 'dynamic_eval' / 'fixed_skills'

STOP = set("""echo then fi if for done do while bash sh python python3 cat ls cd mkdir rm cp mv grep sed awk
exit return true false set local export fi; then; else elif esac case in of the and or not is are was were
this that with from into file files path line lines true false null none var tmp usr bin etc app workspace
jq curl git gh npm node import def class return print len str int list dict open read write json yaml
""".split())

TOKEN = re.compile(r"""
    `[^`\n]{2,60}`                                  # backticked code inside prose
  | --[A-Za-z][\w-]*                                # long CLI flags
  | (?<![\w-])-[A-Za-z](?![\w-])                    # short CLI flags
  | "[^"\n]{2,60}" | '[^'\n]{2,60}'                 # string literals
  | \b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b       # snake_case identifiers
  | \b[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+\b      # dotted names / paths
  | \b[A-Za-z0-9]*-[A-Za-z][A-Za-z0-9-]*\b           # hyphenated compounds (in-progress)
  | \b\d{2,}\b                                     # numbers
  | [A-Za-z0-9_./-]*/[A-Za-z0-9_./-]+               # path-like
""", re.X)

# tokens that are too generic to discriminate a trajectory
GENERIC = re.compile(r'^[a-z][a-z-]{2,}$')


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors='strict')
    except Exception:
        return None


def anchors_from(lines: list[str]) -> list[str]:
    """Code-like tokens only: prose words cannot be matched against a trajectory."""
    out, seen = [], set()
    for ln in lines:
        for m in TOKEN.findall(ln):
            t = m.strip('`"\'')
            low = t.lower()
            if len(t) < 3 or low in STOP:
                continue
            if GENERIC.match(t) and '_' not in t and '-' not in t:
                continue          # plain lowercase English word
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def skill_files(root: Path) -> dict[str, Path]:
    base = root
    if not base.is_dir():
        return {}
    files = {}
    for p in base.rglob('*'):
        if p.is_file():
            files[str(p.relative_to(base))] = p
    return files


def checks_of(task: str) -> dict[str, str]:
    """check name -> source text"""
    found = {}
    for d in ('verifier', 'oracle'):
        for p in (TASKS / task / d).rglob('*.py') if (TASKS / task / d).is_dir() else []:
            txt = read_text(p) or ''
            for m in re.finditer(r'def (check_[A-Za-z0-9_]+)\s*\(', txt):
                found[m.group(1)] = txt

    return found


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta: dict[str, dict] = {}
    for t in json.load(open(REGISTRY))['tasks']:
        meta[t['task']] = {'types': [x.strip() for x in t.get('types', []) if x.strip()],
                           'skill': t.get('skill'), 'batch': 'batch25',
                           'env_deps': t.get('env_deps')}
    for t in json.load(open(REGISTRY_B13))['tasks']:
        meta.setdefault(t['task'], {}).update(
            {'types': [x.strip() for x in t.get('types', []) if x.strip()],
             'skill': t.get('skill'), 'batch': 'batch13',
             'env_deps': t.get('expectation')})
    for e in json.load(open(REGISTRY_B12)):
        if e.get('corpus') != 'wildskills-12':
            continue
        m = meta.setdefault(e['task'], {'types': [], 'batch': 'batch12'})
        m['batch'] = 'batch12'
        m.setdefault('legacy_type', e.get('type'))
        m.setdefault('summary', e.get('summary'))
        m.setdefault('changed_files_registry', e.get('changed_files'))
    rows = []
    local_tasks = sorted(p.name for p in TASKS.iterdir() if p.is_dir())
    for task in local_tasks:
        meta.setdefault(task, {'types': [], 'batch': 'unknown'})
        src = skill_files(TASKS / task / 'environment' / 'skills')
        dst = skill_files(FIXED / task / 'environment' / 'skills')
        changed, removed_all, added_all, per_file = [], [], [], {}
        for rel in sorted(set(src) | set(dst)):
            a, b = src.get(rel), dst.get(rel)
            if a and b and a.read_bytes() == b.read_bytes():
                continue
            ta = read_text(a) if a else None
            tb = read_text(b) if b else None
            if ta is None and tb is None:
                changed.append(rel)
                per_file[rel] = {'binary_or_missing': True}
                continue
            d = list(difflib.unified_diff((ta or '').splitlines(), (tb or '').splitlines(),
                                          lineterm='', n=0))
            rem = [l[1:] for l in d if l.startswith('-') and not l.startswith('---')]
            add = [l[1:] for l in d if l.startswith('+') and not l.startswith('+++')]
            changed.append(rel)
            removed_all += rem
            added_all += add
            per_file[rel] = {'removed': rem[:40], 'added': add[:40],
                             'n_removed': len(rem), 'n_added': len(add)}
        anc_old, anc_new = anchors_from(removed_all), anchors_from(added_all)
        only_old = [a for a in anc_old if a not in set(anc_new)]
        only_new = [a for a in anc_new if a not in set(anc_old)]
        chk = checks_of(task)
        related = []
        for name, body in chk.items():
            if not name.startswith('check_'):
                continue
            low = body.lower()
            if any(len(a) >= 5 and a.lower() in low for a in (only_old + only_new)):
                related.append(name)
        rec = {
            'task': task,
            'types': meta[task].get('types', []),
            'batch': meta[task].get('batch'),
            'legacy_type': meta[task].get('legacy_type'),
            'registry_summary': meta[task].get('summary'),
            'skill': meta[task].get('skill'),
            'group': meta[task].get('group'),
            'env_deps': meta[task].get('env_deps'),
            'changed_files': changed,
            'diff': per_file,
            'anchors_shipped_only': only_old[:60],
            'anchors_fixed_only': only_new[:60],
            'related_checks': sorted(related),
            'n_checks_total': len(chk),
        }
        json.dump(rec, open(OUT / f'{task}.json', 'w'), indent=1, ensure_ascii=False)
        rows.append({
            'task': task,
            'batch': rec.get('batch') or '',
            'types': ';'.join(rec['types']) or (rec.get('legacy_type') or ''),
            'skill': rec['skill'],
            'n_changed_files': len(changed),
            'n_anchor_shipped': len(only_old),
            'n_anchor_fixed': len(only_new),
            'n_related_checks': len(related),
            'n_checks_total': len(chk),
            'anchors_shipped': ' | '.join(only_old[:6]),
            'related_checks': ' | '.join(sorted(related)[:4]),
        })
    with open(OUT.parent / 'descriptors.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # summary
    n = len(rows)
    usable = [r for r in rows if r['n_anchor_shipped'] >= 2 and r['n_changed_files'] >= 1]
    withchk = [r for r in rows if r['n_related_checks'] >= 1]
    from collections import Counter
    cls = Counter(c for r in rows for c in r['types'].split(';') if c)
    print(f'tasks={n}  descriptors -> {OUT}')
    print(f'  with >=2 shipped-only anchors and a changed file: {len(usable)}')
    print(f'  with >=1 verifier check tied to an anchor        : {len(withchk)}')
    print('  class distribution:')
    for c, k in cls.most_common():
        print(f'    {c:<48} {k}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
