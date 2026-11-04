#!/usr/bin/env python3
"""Mechanism table for the 25-task study: did the repair actually remove the defects it targets?

Effectiveness and efficiency alone cannot distinguish "the repair worked" from "the model got
lucky". This measures the quantity a doc repair acts on directly:

  * targeted defect counts per arm -- `python: command not found`, `sqlite3: command not found`,
    `externally-managed-environment`, `No module named X` -- where X/command is named in the
    skill text (doc-induced) vs invented by the agent (not doc-induced)

The doc-induced split matters: an aggregate `command not found` count can go UP after a repair
simply because the agent runs longer and tries more unrelated tools. Only the doc-induced
subset is what the repair is supposed to remove.

    python3 analysis_tools/mechanism25.py [--root .]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ORIG10 = ['civ6-adjacency-optimizer', 'court-form-filling',
          'crystallographic-wyckoff-position-analysis', 'data-to-d3', 'dialogue-parser',
          'energy-market-pricing', 'fix-druid-loophole-cve', 'fix-erlang-ssh-cve',
          'grid-dispatch-operator', 'mario-coin-counting']
NEW15 = ['citation-check', 'earthquake-plate-calculation', 'energy-ac-optimal-power-flow',
         'exceltable-in-ppt', 'glm-lake-mendota', 'hvac-control', 'lab-unit-harmonization',
         'manufacturing-equipment-maintenance', 'manufacturing-fjsp-optimization',
         'flood-risk-analysis', 'protein-expression-analysis', 'r2r-mpc-control',
         'sec-financial-report', 'offer-letter-generator', 'weighted-gdp-calc']
ARMS = ['NoSkill', 'OriginalSkill', 'RepairedSkill']

# study dir + how the repaired arm is labelled there
STUDIES = {
    'orig10': [('haiku45-threeway-20260917', {'NoSkill': 'NoSkill', 'OriginalSkill': 'OriginalSkill'}),
               ('experiments/drs-v2-20260925', {'RepairedSkill': 'RepairV2'})],
    'new15': [('experiments/multi25-20260925',
               {'NoSkill': 'NoSkill', 'OriginalSkill': 'OriginalSkill',
                'RepairedSkill': 'RepairedSkill'})],
}
CMD = re.compile(r'(\S+): command not found')
PEP = re.compile(r'externally-managed-environment')
MOD = re.compile(r"No module named '([^']+)'")
DOC_CHECKED = {'cmd': CMD, 'no_module': MOD}


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get('text') or c.get('content') or '')
    return ''


def is_doc_command(stext: str, payload: str) -> bool:
    """Is `payload` used as a COMMAND in the skill text (rather than merely mentioned)?

    The naive test -- "does the token appear in the skill file" -- is wrong for exactly the
    cases that matter. `python` appears in every skill that has a ```python code fence, so
    the naive test calls `python: command not found` doc-induced even when the agent typed it
    out of habit for a script it wrote itself. Requiring a command shape fixes that:
      * `python <script>.py` or `python -m <module>`
      * `pip install ...`
      * a bare token at the start of a fenced bash/sh block line
    """
    esc = re.escape(payload)
    if payload in ('python', 'python3'):
        return bool(re.search(rf'(?<![3\w.]){esc}(?=[ \t]+(?:-m\b|[\w./-]+\.py))', stext))
    if payload in ('pip', 'pip3'):
        return bool(re.search(rf'\b{esc} install\b', stext))
    # a generic command: appears as the first word of a line inside a shell block
    for blk in re.findall(r'```(?:bash|sh|shell|console|zsh)\n(.*?)```', stext, re.S):
        for line in blk.splitlines():
            if line.strip().lstrip('$ ').split()[:1] == [payload]:
                return True
    return False


def skill_text(root: Path, task: str):
    """Concatenated skill text for doc-induced detection. Prefers the study's own copy."""
    for base in (root / 'experiments/multi25-20260925/inputs/selected_tasks',
                 root / 'haiku45-threeway-20260917/inputs/selected_tasks',
                 root / 'tasks'):
        d = base / task / 'environment' / 'skills'
        if d.is_dir():
            t = []
            for p in d.rglob('*'):
                if p.is_file() and p.suffix in ('.md', '.py', '.js', '.sh', '.txt', '.json', '.yaml', '.yml'):
                    try:
                        t.append(p.read_text(errors='replace'))
                    except Exception:
                        pass
            return '\n'.join(t)
    return ''


def scan_trace(p: Path):
    cmd, mod, pep = Counter(), Counter(), 0
    with p.open(errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get('type') != 'user':
                continue
            for c in (o.get('message') or {}).get('content') or []:
                if not isinstance(c, dict) or c.get('type') != 'tool_result':
                    continue
                t = text_of(c.get('content'))
                for m in CMD.finditer(t):
                    cmd[m.group(1)] += 1
                for m in MOD.finditer(t):
                    mod[m.group(1)] += 1
                if PEP.search(t):
                    pep += 1
    return cmd, mod, pep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--out', default='experiments/multi25-20260925/analysis/mechanism-table.md')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    tasks = ORIG10 + NEW15

    # per arm -> Counter of doc-induced / not-doc-induced defects
    agg = {a: dict(doc_cmd=Counter(), nondoc_cmd=Counter(), doc_mod=Counter(),
                   nondoc_mod=Counter(), pep=0, cells=0) for a in ARMS}
    skill_cache = {}
    for group, studies in STUDIES.items():
        for sdir, armmap in studies:
            runs = root / sdir / 'runs'
            if not runs.is_dir():
                continue
            for arm, label in armmap.items():
                for cell in sorted(p for p in runs.iterdir() if p.is_dir()):
                    if f'__{label}__' not in cell.name:
                        continue
                    task = cell.name.split('__')[0]
                    traces = sorted(cell.rglob('cli.stdout.jsonl'))
                    if not traces:
                        continue
                    if task not in skill_cache:
                        skill_cache[task] = skill_text(root, task)
                    stext = skill_cache[task]
                    cmd, mod, pep = scan_trace(traces[0])
                    s = agg[arm]
                    s['cells'] += 1
                    s['pep'] += pep
                    # The NoSkill arm injects an empty skills dir, so the model never sees
                    # the document: nothing it types can be doc-induced, even when the
                    # payload happens to appear in the task's skill text. Matching those
                    # against the (unmounted) skill source would silently turn the blank
                    # control into a second treatment column. It is still worth counting
                    # them -- as the base rate showing the same errors arise with no doc.
                    doc_ok = arm != 'NoSkill'
                    for k, v in cmd.items():
                        (s['doc_cmd'] if doc_ok and is_doc_command(stext, k) else s['nondoc_cmd'])[k] += v
                    for k, v in mod.items():
                        (s['doc_mod'] if doc_ok and k in stext else s['nondoc_mod'])[k] += v

    L = []
    A = L.append
    A('# 机制表：修复是否真的移除了它针对的缺陷\n')
    A('判定 **doc-induced** 的判据是"该名字在 skill 文本里以**命令形态**出现"，而不是"出现过即可"：')
    A('后者会把 ``` 代码围栏 里的 `python` 也算进来，从而把模型自己习惯性敲的 `python xxx.py` 误判为文档诱导。')
    A('具体规则：`python <script>.py` / `python -m <mod>`、`pip install ...`、或 shell 代码块行首的裸命令名。\n')
    A('**怎么读这张表**：')
    A('- `NoSkill` 臂注入的是空目录，模型**从未见过文档**，所以它的 doc-induced 必然为 0 ——')
    A('  这是天然的空白对照。它那些 `No module named X` / `python` 报错被计入**非**文档诱导列，')
    A('  作用是给出**基线发生率**：同样的报错在没有文档时也会发生，')
    A('  所以"载荷名字出现在文档里"本身不足以证明因果。')
    A('- 只有 `OriginalSkill` 与 `RepairedSkill` 的差，才是修复的效果；')
    A('- 但**聚合差也会被 task 组成混淆**：RepairedSkill 臂里既有被修的 task 也有零编辑 task。')
    A('  逐条靶向复核见 `REPAIR-v3-NOTES.md` §8.1（回到 `tool_use` 调用点逐条判读）。')
    A('- 最后一列非文档诱导量是模型自己即兴尝试的工具，**修复后反而更多**（跑得更久、试得更多），')
    A('  所以**绝不能**用 `command not found` 的总量评价修复。\n')
    A('| arm | cells | doc-induced `cmd not found` | doc-induced `No module` | `externally-managed` | **非**文档诱导 `cmd not found` |')
    A('|---|---|---|---|---|---|')
    for a in ARMS:
        s = agg[a]
        A(f"| {a} | {s['cells']} | {sum(s['doc_cmd'].values())} | {sum(s['doc_mod'].values())} | "
          f"{s['pep']} | {sum(s['nondoc_cmd'].values())} |")
    A('\n## 明细（doc-induced）\n')
    A('| arm | 命令 | 次数 |')
    A('|---|---|---|')
    for a in ARMS:
        for k, v in agg[a]['doc_cmd'].most_common():
            A(f'| {a} | `{k}` | {v} |')
        for k, v in agg[a]['doc_mod'].most_common():
            A(f'| {a} | `No module named {k}` | {v} |')
    A('\n## 明细（非文档诱导，用于说明总量为何会误导）\n')
    A('| arm | 命令/模块 | 次数 |')
    A('|---|---|---|')
    for a in ARMS:
        for k, v in agg[a]['nondoc_cmd'].most_common(8):
            A(f'| {a} | `{k}` | {v} |')
        for k, v in agg[a]['nondoc_mod'].most_common(8):
            A(f'| {a} | `No module named {k}` | {v} |')

    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(L) + '\n')
    print('\n'.join(L))
    print(f'\n[written] {out}')


if __name__ == '__main__':
    main()
