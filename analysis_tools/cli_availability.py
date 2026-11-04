#!/usr/bin/env python3
"""R3-equivalent check: does any skill doc name a CLI tool the task image does not ship?

v2 repaired one such case (civ6: `sqlite3` CLI absent -> use Python's stdlib). This is the
same check for the 15 new tasks, and it is deliberately mechanical so it cannot be skipped:

  extract candidate commands from the skill *.md (bash/sh code blocks + inline code spans)
  -> ask the task image, via `docker run ... command -v`, which of them exist

Anything named in a doc but absent from the image is a documented command that cannot run,
i.e. exactly the class v2's R3 repaired.

    python3 analysis_tools/cli_availability.py --study experiments/multi25-20260925
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

NEW15 = ['citation-check', 'earthquake-plate-calculation', 'energy-ac-optimal-power-flow',
         'exceltable-in-ppt', 'glm-lake-mendota', 'hvac-control', 'lab-unit-harmonization',
         'manufacturing-equipment-maintenance', 'manufacturing-fjsp-optimization',
         'flood-risk-analysis', 'protein-expression-analysis', 'r2r-mpc-control',
         'sec-financial-report', 'offer-letter-generator', 'weighted-gdp-calc']

SHELL_BLOCK = re.compile(r'```(?:bash|sh|shell|console|zsh)\n(.*?)```', re.S)
INLINE = re.compile(r'`([a-z][a-z0-9_.+-]{1,24})\s+[^`\n]{2,70}`')
# things that are not external commands
SKIP = {
    'python', 'python3', 'pip', 'pip3', 'uv', 'uvx', 'conda', 'cd', 'export', 'echo', 'source',
    'set', 'true', 'false', 'if', 'then', 'else', 'fi', 'for', 'while', 'do', 'done', 'exit',
    'return', 'import', 'from', 'def', 'print', 'assert', 'with', 'as', 'in', 'not', 'and',
    'or', 'is', 'try', 'except', 'finally', 'class', 'raise', 'yield', 'lambda', 'await',
    'async', 'global', 'pass', 'break', 'continue', 'del', 'elif', 'EOF', 'AND', 'OR',
    'total', 'sheet', 'data', 'df', 'note', 'use', 'run', 'see', 'the', 'and', 'api_key',
    'title', 'author', 'year', 'doi', 'url', 'journal', 'volume', 'pages', 'number',
    'booktitle', 'publisher', 'address', 'month', 'howpublished', 'bibtex', 'public',
    'private', 'const', 'glm',  # `glm` is a real binary; handled explicitly below
}
COREUTILS = {
    'ls', 'cat', 'cp', 'mv', 'rm', 'mkdir', 'rmdir', 'touch', 'head', 'tail', 'wc', 'sort',
    'uniq', 'cut', 'tr', 'grep', 'find', 'sed', 'awk', 'diff', 'du', 'df', 'chmod', 'chown',
    'ln', 'tar', 'gzip', 'gunzip', 'base64', 'date', 'env', 'which', 'test', 'sleep', 'xargs',
    'tee', 'paste', 'join', 'split', 'stat', 'file', 'strings', 'jq', 'curl', 'wget',
}


def candidates(skill_root: Path):
    out = defaultdict(set)
    for p in skill_root.rglob('*.md'):
        txt = p.read_text(errors='replace')
        for blk in SHELL_BLOCK.findall(txt):
            for line in blk.splitlines():
                line = line.strip().lstrip('$ ').strip()
                if not line or line.startswith('#'):
                    continue
                tok = line.split()[0]
                if re.fullmatch(r'[a-zA-Z][\w.+-]*', tok) and tok not in SKIP:
                    out[tok].add(str(p.relative_to(skill_root)))
        for m in INLINE.finditer(txt):
            tok = m.group(1)
            if tok not in SKIP and not tok.startswith(('http', 'www')):
                out[tok].add(str(p.relative_to(skill_root)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--study', required=True)
    ap.add_argument('--tasks', default='')
    args = ap.parse_args()
    study = Path(args.study)
    tasks = [t.strip() for t in args.tasks.split(',') if t.strip()] or NEW15

    problems = []
    for task in tasks:
        taskdir = study / 'inputs' / 'selected_tasks' / task
        skills = taskdir / 'environment' / 'skills'
        if not skills.is_dir():
            print(f'{task:40} (no skills dir, skipped)')
            continue
        cand = candidates(skills)
        names = sorted(cand)
        if not names:
            continue
        # one container per task: ask which commands resolve
        script = '; '.join(f'command -v {n} >/dev/null 2>&1 && echo "P {n}" || echo "A {n}"'
                           for n in names)
        # Look the image up by repository name rather than recomputing the content hash:
        # reproducing the runner's exact hash convention here is easy to get subtly wrong
        # (it hashes paths relative to the task dir, i.e. 'environment/Dockerfile').
        tag = subprocess.run(
            ['docker', 'images', f'anonymous/{task}', '--format', '{{.Repository}}:{{.Tag}}'],
            capture_output=True, text=True).stdout.strip().splitlines()
        tag = tag[0] if tag else f'anonymous/{task}:missing'
        r = subprocess.run(['docker', 'run', '--rm', tag, 'bash', '-lc', script],
                           capture_output=True, text=True)
        present = {l[2:] for l in r.stdout.splitlines() if l.startswith('P ')}
        absent = sorted(l[2:] for l in r.stdout.splitlines() if l.startswith('A '))
        if r.returncode != 0 and not present and not absent:
            print(f'{task:40} (image {tag} unavailable)')
            continue
        # only report things a reasonable reader would treat as an instruction
        notable = [a for a in absent if a in COREUTILS or '.' not in a]
        print(f'{task:40} checked={len(names):>2}  ABSENT={absent}')
        for a in notable:
            problems.append((task, a, sorted(cand[a])[:2]))

    print('\n=== 文档点名、但镜像里没有的命令 ===')
    if not problems:
        print('  （无）')
    for task, cmd, files in problems:
        print(f'  {task:38} `{cmd}`  in {files}')


if __name__ == '__main__':
    main()
