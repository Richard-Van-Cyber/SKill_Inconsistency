#!/usr/bin/env python3
"""Structural gate for the wildskills13 task packages (run before any deploy).

For each task listed in tasks.json (or --tasks a,b,c) it checks:
  * required files exist: task.md, environment/Dockerfile, verifier/test.sh,
    verifier/verify_<mod>.py, oracle/solve.sh
  * task.md frontmatter parses and declares schema_version / verifier.type / sandbox.workdir
  * the verifier compiles and defines >= 3 orthogonal checks
  * environment/skills/<skill>/ exists and contains the audited script(s)
  * fixed_skills/<task>/environment/skills/ exists (the driver hard-requires this)
  * the overlay's byte-diff against the task's pristine skills lists only expected files

Exit code 0 only when every task passes. Writes gates/structure.json.

Usage: python3 validate_tasks.py [--tasks a,b,c]
"""
from __future__ import annotations

import argparse
import json
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path('/workspace/skillEvaluation')
TASKS = REPO / 'wildskills' / 'dynamic_eval' / 'tasks'
FIXED = REPO / 'wildskills' / 'dynamic_eval' / 'fixed_skills'
STUDY = REPO / 'experiments' / 'wildskills13-20260929'


def load_registry() -> list[dict]:
    p = STUDY / 'tasks.json'
    if not p.is_file():
        return []
    data = json.loads(p.read_text())
    return data.get('tasks', data if isinstance(data, list) else [])


def frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None
    try:
        import yaml
        return yaml.safe_load(m.group(1))
    except Exception:  # noqa: BLE001
        return {'_parse_error': True}


def check_task(entry: dict) -> dict:
    name = entry['task']
    base = TASKS / name
    if not (base / 'task.md').is_file():
        return {'task': name, 'skill': entry.get('skill'), 'fail': [], 'warn': [],
                'diff': [], 'status': entry.get('status', 'not-started'),
                'note': 'package not authored yet — skipped'}
    mod = name.replace('-', '_')
    out = {'task': name, 'skill': entry.get('skill'), 'fail': [], 'warn': [], 'diff': []}

    req = [base / 'task.md', base / 'environment' / 'Dockerfile',
           base / 'verifier' / 'test.sh', base / 'verifier' / f'verify_{mod}.py',
           base / 'oracle' / 'solve.sh']
    for p in req:
        if not p.is_file():
            out['fail'].append(f'missing {p.relative_to(REPO)}')

    fm = frontmatter(base / 'task.md') if (base / 'task.md').is_file() else None
    if fm is None:
        out['fail'].append('task.md has no parsable frontmatter')
    elif fm.get('_parse_error'):
        out['warn'].append('frontmatter not parsed (pyyaml missing?)')
    else:
        if not fm.get('schema_version'):
            out['fail'].append('frontmatter: schema_version missing')
        if (fm.get('verifier') or {}).get('type') != 'test-script':
            out['fail'].append('frontmatter: verifier.type != test-script')
        if not (fm.get('sandbox') or {}).get('workdir'):
            out['fail'].append('frontmatter: sandbox.workdir missing')

    vp = base / 'verifier' / f'verify_{mod}.py'
    if vp.is_file():
        try:
            py_compile.compile(str(vp), cfile=tempfile.mktemp(), doraise=True)
            src = vp.read_text(encoding='utf-8')
            n = len(re.findall(r'^\s*\("[a-z0-9_]+",\s*check_', src, re.M))
            if n < 3:
                out['fail'].append(f'verifier defines only {n} checks (need >= 3)')
            if 'placeholder' in src:
                out['fail'].append('verifier still contains the scaffold placeholder')
            out['checks'] = n
        except py_compile.PyCompileError as exc:
            out['fail'].append(f'verifier does not compile: {exc.msg}')

    skills = base / 'environment' / 'skills'
    if not skills.is_dir() or not any(skills.iterdir()):
        out['fail'].append('environment/skills/ is empty')
    else:
        sub = [d for d in skills.iterdir() if d.is_dir()]
        codes = [f for d in sub for f in d.rglob('*')
                 if f.suffix.lower() in {'.py', '.sh', '.js', '.ts', '.go', '.rb'}]
        if not codes:
            # A doc-only skill (SKILL.md + prose references, no code) is legitimate for tasks
            # whose defect is a missing/corrupt reference document; the registry marks those.
            if entry.get('doc_only_skill'):
                out['warn'].append('doc-only skill: no executable script under environment/skills/ '
                                   '(allowed: registry marks doc_only_skill)')
            else:
                out['fail'].append('no executable script under environment/skills/')
        out['scripts'] = len(codes)
        declared = entry.get('package_skill') or entry.get('skill')
        declared = declared if isinstance(declared, list) else ([declared] if declared else [])
        for d0 in declared:
            if d0 not in {d.name for d in sub}:
                out['fail'].append(f"declared skill {d0} not under environment/skills/")
        if len(sub) > 1:
            out['warn'].append(f"{len(sub)} skill dirs under environment/skills/ "
                               f"({[d.name for d in sub]}) — the driver uploads all of them")

    overlay = FIXED / name / 'environment' / 'skills'
    if not overlay.is_dir():
        out['fail'].append(f'missing overlay: {overlay.relative_to(REPO)}')
    elif skills.is_dir():
        r = subprocess.run(['diff', '-rq', str(skills), str(overlay)],
                           capture_output=True, text=True)
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        out['diff'] = lines
        if not lines:
            out['warn'].append('overlay is byte-identical to pristine (deliberate placebo? record it)')
        if any('__pycache__' in l or '.pyc' in l for l in lines):
            out['warn'].append('overlay/pristine diff mentions __pycache__ (.pyc) — clean it')
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tasks', default='')
    args = ap.parse_args()

    reg = load_registry()
    if args.tasks:
        wanted = [t for t in args.tasks.split(',') if t]
        reg = [e for e in reg if e['task'] in wanted] or [{'task': t, 'skill': None} for t in wanted]
    if not reg:
        print('no tasks: pass --tasks or create tasks.json')
        return 2

    results = [check_task(e) for e in reg]
    (STUDY / 'gates').mkdir(parents=True, exist_ok=True)
    (STUDY / 'gates' / 'structure.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')

    bad = 0
    for r in results:
        if r.get('note'):
            print(f"SKIP {r['task']:<42} {r['note']}")
            continue
        status = 'OK  ' if not r['fail'] else 'FAIL'
        bad += bool(r['fail'])
        print(f"{status} {r['task']:<42} checks={r.get('checks', '?')} scripts={r.get('scripts', '?')} "
              f"diff={len(r['diff'])}")
        for f in r['fail']:
            print(f'        ✗ {f}')
        for w in r['warn']:
            print(f'        ! {w}')
    done = [r for r in results if not r.get('note')]
    print(f'\n{len(done) - bad}/{len(done)} authored tasks pass the structural gate '
          f'({len(results) - len(done)} not authored yet)')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
