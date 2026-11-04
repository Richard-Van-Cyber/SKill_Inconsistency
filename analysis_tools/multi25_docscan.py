#!/usr/bin/env python3
"""Static (doc vs image) + dynamic (paper-v1 traces) cross-check for the 15 new tasks.

For each task it answers, per candidate defect:
  * is it STATICALLY present -- does a doc reference something the Dockerfile does not provide?
  * is it DYNAMICALLY observed -- did a real run (SkillsBench paper-v1 with-skills arm) hit it?
  * is it DOC-INDUCED -- does the referenced token actually appear in the skill tree?

Only defects that are all three are worth editing, and the edit must be a doc statement
(never a code change), per the three repair principles.

    python3 analysis_tools/multi25_docscan.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('.')
NEW15 = ['citation-check', 'earthquake-plate-calculation', 'energy-ac-optimal-power-flow',
         'exceltable-in-ppt', 'glm-lake-mendota', 'hvac-control', 'lab-unit-harmonization',
         'manufacturing-equipment-maintenance', 'manufacturing-fjsp-optimization',
         'flood-risk-analysis', 'protein-expression-analysis', 'r2r-mpc-control',
         'sec-financial-report', 'offer-letter-generator', 'weighted-gdp-calc']
TRAJ = json.loads(Path('/tmp/skillsbench_traj_mining.json').read_text())

BARE_PY = re.compile(r'(?<![3\w.])python (?=[\w./-]+\.py|\$|-)')
BARE_PIP = re.compile(r'(?<![-\w])pip3? install(?![^\n]*break-system-packages)')
IMP = re.compile(r'^\s*(?:import|from)\s+([A-Za-z_][\w]*)', re.M)
STDLIB = set("""os sys re json math time datetime pathlib subprocess shutil glob argparse
collections itertools functools typing dataclasses enum csv io string random statistics
textwrap copy tempfile sqlite3 warnings logging hashlib base64 zipfile tarfile gzip
unittest traceback inspect abc contextlib urllib xml html email smtplib socket threading
multiprocessing asyncio concurrent pickle struct binascii uuid secrets decimal fractions
numbers operator bisect heapq array weakref gc platform getpass pprint difflib""".split())


def dockerfile_facts(task_dir: Path):
    df = task_dir / 'environment' / 'Dockerfile'
    txt = df.read_text(errors='replace') if df.exists() else ''
    base = next((l.split()[1] for l in txt.splitlines() if l.startswith('FROM')), '?')
    pip = set()
    apt = set()
    for line in txt.splitlines():
        if 'pip' in line and 'install' in line:
            for tok in re.findall(r'[A-Za-z_][\w.\-]*==[\w.\-]+|[A-Za-z_][\w.\-]{2,}', line):
                if '==' in tok or (tok not in ('pip', 'pip3', 'install', 'RUN') and not tok.isupper()):
                    pip.add(tok.split('==')[0])
        if 'apt-get install' in line or 'apt install' in line:
            for tok in re.findall(r'(?<!-)\b[a-z][\w.+-]{2,}\b', line):
                if tok not in ('apt', 'get', 'install', 'update', 'y', 'qq', 'rm', 'rf', 'var', 'lib', 'lists'):
                    apt.add(tok)
    return base, pip, apt, txt


def main():
    print(f"{'task':44}{'base':<24}{'bare python':>12}{'bare pip':>9}{'imports not in image':>22}"
          f"{'dyn hits':>9}")
    print('-' * 130)
    findings = {}
    for task in NEW15:
        td = ROOT / 'tasks' / task
        base, pip, apt, dftxt = dockerfile_facts(td)
        skills = td / 'environment' / 'skills'
        docs = [p for p in skills.rglob('*') if p.is_file() and p.suffix in
                ('.md', '.py', '.js', '.sh', '.txt', '.json', '.yaml', '.yml')]
        bare_py = 0
        bare_pip = 0
        imports = Counter()
        for p in docs:
            try:
                txt = p.read_text(errors='replace')
            except Exception:
                continue
            bare_py += len(BARE_PY.findall(txt))
            bare_pip += len(BARE_PIP.findall(txt))
            if p.suffix == '.py':
                for m in IMP.finditer(txt):
                    imports[m.group(1)] += 1
        missing = sorted(n for n in imports
                         if n not in STDLIB and n not in pip
                         and n.lower().replace('-', '_') not in {x.lower().replace('-', '_') for x in pip})
        dyn = Counter()
        for r in TRAJ.get(task, []):
            for k, v in (r.get('detail') or {}).items():
                if k in ('cmd_not_found', 'no_module', 'pep668', 'file_too_big', 'eisdir'):
                    dyn.update({f'{k}:{kk}': vv for kk, vv in v.items()})
        findings[task] = dict(base=base, bare_python=bare_py, bare_pip=bare_pip,
                              missing=missing[:12], dynamic=dict(dyn))
        print(f'{task:44}{base:<24}{bare_py:>12}{bare_pip:>9}{",".join(missing[:3])[:22]:>22}'
              f'{sum(dyn.values()):>9}')
    Path('/tmp/multi25_docscan.json').write_text(json.dumps(findings, ensure_ascii=False, indent=1))

    print('\n\n===== 逐 task 细节（静态缺口 vs 动态命中）=====')
    for task, f in findings.items():
        print(f'\n## {task}   base={f["base"]}')
        if f['bare_python']:
            print(f'   [静态] 文档裸 `python` {f["bare_python"]} 处  -> R2 型（镜像通常只有 python3）')
        if f['bare_pip']:
            print(f'   [静态] 文档裸 `pip install` {f["bare_pip"]} 处  -> R1 型（PEP 668 会拦）')
        if f['missing']:
            print(f'   [静态] 文档脚本 import 但镜像未装的包: {f["missing"]}')
        if f['dynamic']:
            print(f'   [动态] paper-v1 轨迹命中: {f["dynamic"]}')


if __name__ == '__main__':
    main()
