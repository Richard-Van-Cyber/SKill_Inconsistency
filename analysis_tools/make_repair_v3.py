#!/usr/bin/env python3
"""Generate `fixed_skills_v3` for the 15 new tasks -- doc-only, minimal, trace-evidenced.

Repair families (each must be justified by THIS study's OriginalSkill traces before it is
applied; the static scan only proposes candidates):

  F1 interpreter   in *.md only:  `python <script>.py` / `python -m <mod>`  ->  python3
                   The image ships python3 only (ubuntu:24.04 and python:*-slim alike),
                   so the documented command cannot run as written.
  F2 dependency    in *.md only:  a documented bare `pip install ...` gets the
                   `--break-system-packages` form that the task's own oracle uses.
                   On ubuntu:24.04 a bare pip is refused (PEP 668).

Deliberately NOT touched, to keep the "documentation only" claim unambiguous:
  * any *.py file, including docstrings that mention an interpreter
    (a printed usage string is not an instruction the agent executes)
  * any data or script file under environment/

    python3 analysis_tools/make_repair_v3.py [--apply]
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path('.')
NEW15 = ['citation-check', 'earthquake-plate-calculation', 'energy-ac-optimal-power-flow',
         'exceltable-in-ppt', 'glm-lake-mendota', 'hvac-control', 'lab-unit-harmonization',
         'manufacturing-equipment-maintenance', 'manufacturing-fjsp-optimization',
         'flood-risk-analysis', 'protein-expression-analysis', 'r2r-mpc-control',
         'sec-financial-report', 'offer-letter-generator', 'weighted-gdp-calc']
DEST = ROOT / 'fixed_skills_v3'

# `python script.py` or `python -m mod`, but never `python3`
INTERP = re.compile(r'(?<![3\w.])python(?=[ \t]+(?:-m\b|[\w./-]+\.py))')
# a documented bare pip install (skip ones already carrying the flag)
BARE_PIP = re.compile(r'(?<![-\w])pip3? install(?![^\n]*break-system-packages)')


# F3 -- environment fact. A skill *.md whose code samples import a package the image does
# not install, AND whose absence is evidenced in a real trace, gets one short notes block.
# Without it the documented example cannot run at all: `import numpy` -> ModuleNotFoundError,
# and the obvious recovery (`pip install numpy`) is refused by PEP 668.
# Only applied to files that carry NO pip line already -- those were handled by F2, and a
# second note there would be redundant.
#
# install_cmd is taken from the task's own oracle wherever the oracle installs them, so the
# command in the doc is the one the task author verified rather than one I invented.
F3: dict[str, dict[str, tuple[str, list[str]]]] = {
    'energy-ac-optimal-power-flow': {
        # oracle/solve.sh:9 -- verified by the task author
        'power-flow-data/SKILL.md': (
            'pip3 install --break-system-packages numpy==1.26.4 casadi==3.6.7 -q',
            ['numpy', 'scipy', 'casadi']),
        'ac-branch-pi-model/SKILL.md': (
            'pip3 install --break-system-packages numpy==1.26.4 casadi==3.6.7 -q',
            ['numpy', 'scipy', 'casadi']),
    },
    'protein-expression-analysis': {
        'xlsx/SKILL.md': ('pip3 install --break-system-packages pandas -q',
                          ['pandas', 'numpy']),
    },
    'weighted-gdp-calc': {
        'xlsx/SKILL.md': ('pip3 install --break-system-packages pandas -q',
                          ['pandas', 'numpy']),
    },
}


def f3_note(pkgs, cmd):
    return (
        "## Environment Setup\n\n"
        + ", ".join(f"`{p}`" for p in pkgs)
        + " " + ("is" if len(pkgs) == 1 else "are")
        + " **not** preinstalled in this container, and a bare `pip install` is blocked\n"
        "(the environment is externally managed: `error: externally-managed-environment`).\n"
        "Install once, before the first import:\n\n"
        f"```bash\n{cmd}\n```\n\n"
    )


def apply_f3(task, base, text):
    """Insert the notes block right after the H1 title. Returns (text, applied)."""
    spec = F3.get(task, {})
    if not spec or 'pip install' in text:
        return text, False
    # match on the file's own path -- caller passes it via base
    if base not in spec:
        return text, False
    pkgs, cmd = spec[base]
    try:
        i = text.index('\n', text.index('# ')) + 1
    except ValueError:
        return text, False
    cmd_s, pkgs_s = spec[base]        # table is (install_cmd, packages)
    return text[:i] + '\n' + f3_note(pkgs_s, cmd_s) + text[i:], True


# F4 -- a repair already validated end-to-end by the adversarial protocol.
# `offer-letter-generator`'s docx skill handles a conditional block ONLY when both markers
# sit in the same paragraph, while real templates split them across paragraphs. adv/02
# built adversarial data that triggers this (markers pushed into paragraphs 27/28), showed
# the OriginalSkill arm leaving {{END_IF_RELOCATION}} behind (1/3 runs, verifier_error), and
# the repaired text passing 3/3 -- i.e. L1 trigger / L2 attribution / L3 avoidance all held.
# Reusing it here is deliberate: this family's wording is not invented for this study.
#
# Mapping: task -> (destination path inside environment/skills, source file to copy)
F4 = {
    'offer-letter-generator': (
        'docx/SKILL.md',
        'adv/02-offer-letter-generator/repair/docx.SKILL.repaired.md',
    ),
}


def apply_f4(task, skills_root: Path):
    spec = F4.get(task)
    if not spec:
        return False
    dest_rel, src_rel = spec
    src = ROOT / src_rel
    dest = skills_root / dest_rel
    if not src.is_file() or not dest.is_file():
        return False
    new = src.read_text(errors='replace')
    if dest.read_text(errors='replace') == new:
        return False
    dest.write_text(new)
    return True


def apply_f1(text: str):
    return INTERP.subn('python3', text)


def apply_f2(text: str):
    return BARE_PIP.subn('pip3 install --break-system-packages', text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--tasks', default='')
    args = ap.parse_args()
    tasks = [t.strip() for t in args.tasks.split(',') if t.strip()] or NEW15

    if args.apply:
        if DEST.exists():
            shutil.rmtree(DEST)
        for t in tasks:
            (DEST / t / 'environment').mkdir(parents=True, exist_ok=True)
            shutil.copytree(ROOT / 'tasks' / t / 'environment' / 'skills',
                            DEST / t / 'environment' / 'skills')

    print(f"{'task':40}{'F1 files':>9}{'F1 subs':>9}{'F2 files':>9}{'F2 subs':>9}   F1 targets")
    print('-' * 120)
    total = dict(f1f=0, f1s=0, f2f=0, f2s=0)
    for t in tasks:
        base = (DEST if args.apply else ROOT / 'tasks') / t / 'environment' / 'skills'
        if not base.is_dir():
            print(f'{t:40}  (missing skills dir)')
            continue
        f1f = f1s = f2f = f2s = f3f = f3s = 0
        f4f = 0
        targets = []
        if args.apply and apply_f4(t, base):
            f4f = 1
            targets.append('F4:' + F4[t][0])
        for p in sorted(base.rglob('*.md')):
            try:
                txt = p.read_text(errors='replace')
            except Exception:
                continue
            new, n1 = apply_f1(txt)
            new, n2 = apply_f2(new)
            rel = str(p.relative_to(base))
            new, n3 = apply_f3(t, rel, new)
            if n1 or n2 or n3:
                if n1:
                    f1f += 1
                    f1s += n1
                    targets.append(str(p.relative_to(base)))
                if n2:
                    f2f += 1
                    f2s += n2
                if n3:
                    f3f += 1
                    f3s += 1
                if args.apply:
                    p.write_text(new)
        total['f1f'] += f1f; total['f1s'] += f1s; total['f2f'] += f2f; total['f2s'] += f2s
        total['f3f'] = total.get('f3f', 0) + f3f; total['f3s'] = total.get('f3s', 0) + f3s
        total['f4f'] = total.get('f4f', 0) + f4f
        print(f'{t:40}{f1f:>9}{f1s:>9}{f2f:>9}{f2s:>9}   {", ".join(targets[:2])[:60]}')
    print('-' * 120)
    print(f'{"TOTAL":40}{total["f1f"]:>9}{total["f1s"]:>9}{total["f2f"]:>9}{total["f2s"]:>9}')

    if args.apply:
        # integrity: identical file set, only .md edited
        print('\n=== integrity check ===')
        for t in tasks:
            src = ROOT / 'tasks' / t / 'environment' / 'skills'
            dst = DEST / t / 'environment' / 'skills'
            a = sorted(str(p.relative_to(src)) for p in src.rglob('*') if p.is_file())
            b = sorted(str(p.relative_to(dst)) for p in dst.rglob('*') if p.is_file())
            changed = [x for x in a if (dst / x).read_bytes() != (src / x).read_bytes()]
            bad = [x for x in changed if not x.endswith('.md')]
            sa = sum(p.stat().st_size for p in src.rglob('*') if p.is_file())
            sb = sum(p.stat().st_size for p in dst.rglob('*') if p.is_file())
            flag = 'OK' if not bad and a == b else f'!! non-md changed: {bad[:3]}'
            print(f'  {t:40} files {len(a)}->{len(b)}  bytes {sa:,}->{sb:,} '
                  f'({(sb-sa)/sa*100:+.3f}%)  changed={len(changed)} {flag}')


if __name__ == '__main__':
    main()
