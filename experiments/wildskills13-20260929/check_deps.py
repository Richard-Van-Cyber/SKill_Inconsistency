#!/usr/bin/env python3
"""Pre-flight dependency lint for the wildskills13 task packages (a weak, local G1).

For every task it collects the top-level modules imported by the task's own python files
(verifier, oracle) and by the skill scripts it ships, classifies each as stdlib / third-party /
local, and checks that the Dockerfile actually installs the third-party ones (pip or apt).

This catches the failure mode where a verifier imports e.g. `openpyxl` or `pypdf` but the image
never installs it — which would only surface as `verifier_error` after a real run.

Usage: python3 check_deps.py [--tasks a,b,c]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path('/workspace/skillEvaluation')
STUDY = REPO / 'experiments' / 'wildskills13-20260929'
TASKS = REPO / 'wildskills' / 'dynamic_eval' / 'tasks'
FIXED = REPO / 'wildskills' / 'dynamic_eval' / 'fixed_skills'

STDLIB = set(sys.stdlib_module_names)
# module name -> the token that must appear in the Dockerfile (pip/apt package or import name)
PIP_TOKENS = {
    'yaml': ('pyyaml', 'python3-yaml'),
    'pypdf': ('pypdf',), 'PyPDF2': ('pypdf', 'pypdf2'),
    'openpyxl': ('openpyxl',),
    'reportlab': ('reportlab',),
    'pdfplumber': ('pdfplumber',),
    'PIL': ('pillow', 'pil'),
    'numpy': ('numpy',), 'pandas': ('pandas',), 'matplotlib': ('matplotlib',),
    'requests': ('requests',), 'promql_parser': ('promql-parser', 'promql_parser'),
    'django': ('django',), 'lxml': ('lxml',), 'defusedxml': ('defusedxml',),
    'akshare': ('akshare',),
}
APT_TOKENS = {'git': ('git',), 'jq': ('jq',), 'node': ('node',), 'curl': ('curl',)}


def imported_modules(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split('.')[0])
    return mods


def shell_binaries(path: Path) -> set[str]:
    text = path.read_text(encoding='utf-8', errors='replace')
    return {m for b in ('git', 'jq', 'node', 'npm', 'curl', 'bash')
            if (m := b) and re.search(rf'(^|[^\w-]){b}\b', text)}


def check(entry: dict) -> dict:
    name = entry['task']
    base = TASKS / name
    out = {'task': name, 'missing': [], 'external': [], 'dockerfile': None}
    dockerfile = base / 'environment' / 'Dockerfile'
    df_text = dockerfile.read_text(encoding='utf-8', errors='replace') if dockerfile.is_file() else ''
    out['dockerfile'] = str(dockerfile.relative_to(REPO)) if dockerfile.is_file() else None

    py_files = []
    for sub in ('verifier', 'oracle'):
        d = base / sub
        if d.is_dir():
            py_files += [p for p in d.rglob('*.py')]
    skills = base / 'environment' / 'skills'
    if skills.is_dir():
        py_files += [p for p in skills.rglob('*.py')]

    # A module is local when a <module>.py file ships anywhere inside the task package
    # (skill tree OR oracle/verifier), so sibling helper scripts are not mistaken for PyPI deps.
    local_names = set()
    if skills.is_dir():
        local_names |= {p.name for p in skills.rglob('*') if p.is_dir()}
    for scan_root in (base / 'environment', base / 'verifier', base / 'oracle'):
        if scan_root.is_dir():
            local_names |= {p.stem for p in scan_root.rglob('*.py')}
    local_names |= {'verify_' + name.replace('-', '_'), name.replace('-', '_')}

    mods: dict[str, set[str]] = {}
    for p in py_files:
        for m in imported_modules(p):
            mods.setdefault(m, set()).add(str(p.relative_to(REPO)))

    for m, where in sorted(mods.items()):
        if m in STDLIB or m in local_names or m.startswith('_'):
            continue
        tokens = PIP_TOKENS.get(m, (m.lower(),))
        if not any(tok and tok.lower() in df_text.lower() for tok in tokens):
            out['missing'].append({'module': m, 'looked_for': list(tokens),
                                   'used_by': sorted(where)[:3]})
        else:
            out['external'].append(m)

    # shell tools referenced by shipped scripts / verifier
    for p in list((skills.rglob('*.sh') if skills.is_dir() else [])) + \
             list((base / 'verifier').rglob('*.sh') if (base / 'verifier').is_dir() else []):
        for b in shell_binaries(p):
            toks = APT_TOKENS.get(b, (b,))
            if not any(t in df_text.lower() for t in toks):
                out['missing'].append({'module': f'<binary {b}>', 'looked_for': list(toks),
                                       'used_by': [str(p.relative_to(REPO))]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tasks', default='')
    args = ap.parse_args()

    reg = json.loads((STUDY / 'tasks.json').read_text())['tasks']
    if args.tasks:
        wanted = [t for t in args.tasks.split(',') if t]
        reg = [e for e in reg if e['task'] in wanted]
    # only check packages that exist on disk
    reg = [e for e in reg if (TASKS / e['task'] / 'task.md').is_file()]
    if not reg:
        print('no task packages on disk yet')
        return 0

    results = [check(e) for e in reg]
    (STUDY / 'gates').mkdir(parents=True, exist_ok=True)
    (STUDY / 'gates' / 'deps.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')

    bad = 0
    for r in results:
        flag = 'OK  ' if not r['missing'] else 'WARN'
        bad += bool(r['missing'])
        print(f"{flag} {r['task']:<24} external={r['external'] or '—'}")
        for m in r['missing']:
            print(f"        ✗ {m['module']} used by {m['used_by']} but Dockerfile lacks "
                  f"{m['looked_for']}")
    print(f"\n{len(results) - bad}/{len(results)} tasks declare every third-party dependency")
    return 0


if __name__ == '__main__':
    sys.exit(main())
