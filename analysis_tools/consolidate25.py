#!/usr/bin/env python3
"""Consolidate the 25-task x 3-arm experiment into one tidy dataset for the paper.

Sources
-------
original 10 tasks : NoSkill + OriginalSkill   <- haiku45-threeway-20260917/runs
                    RepairedSkill (v2)        <- experiments/drs-v2-20260925/runs
new 15 tasks      : NoSkill + OriginalSkill + RepairedSkill (v3)
                                              <- experiments/multi25-20260925/runs

Emits, under <out>/:
  cells.csv        one row per cell, flat, spreadsheet-ready
  cells.jsonl      same, with the nested fields kept (skills, error counts)
  summary.md       per-task and overall effectiveness + efficiency
  manifest.json    provenance: which study dir each arm came from + file counts

Keeps, per cell: arm, task, trial, status, score, api_calls, agent_seconds,
total_tokens, prompt/completion tokens, budget stop reason, config seconds,
and the path to the trace so the raw trajectory stays one hop away.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
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
VERIFIER_DEFECT = {'court-form-filling'}

SRC = {
    ('NoSkill', 'orig10'): 'haiku45-threeway-20260917',
    ('OriginalSkill', 'orig10'): 'haiku45-threeway-20260917',
    ('RepairedSkill', 'orig10'): 'experiments/drs-v2-20260925',
    # the v2 study labelled its repaired arm RepairV2
    ('RepairedSkill', 'orig10_label'): 'RepairV2',
    ('NoSkill', 'new15'): 'experiments/multi25-20260925',
    ('OriginalSkill', 'new15'): 'experiments/multi25-20260925',
    ('RepairedSkill', 'new15'): 'experiments/multi25-20260925',
}


def arm_dir(study: Path, task: str, arm: str, label: str | None):
    names = [f'{task}__{label}__r{i}' for i in (1, 2, 3)] if label else \
            [f'{task}__{arm}__r{i}' for i in (1, 2, 3)]
    return [study / 'runs' / n for n in names]


def trace_path(cell: Path):
    hits = sorted(cell.rglob('cli.stdout.jsonl'))
    return str(hits[0]) if hits else ''


def truncated(r):
    return r.get('budget_stop_reason') == 'api_budget'


def collect(rowdir: Path, task: str, arm: str, study: Path, label=None):
    out = []
    for cell in arm_dir(study, task, arm, label):
        rj = cell / 'result.json'
        if not rj.exists():
            continue
        r = json.loads(rj.read_text())
        out.append(dict(
            task=task, arm=arm, trial=cell.name.split('__')[-1],
            logical_run_id=cell.name, status=r.get('status'),
            score=r.get('score'),
            raw_reward=r.get('raw_reward'),
            truncated=truncated(r), budget_stop_reason=r.get('budget_stop_reason'),
            termination_reason=r.get('termination_reason'),
            api_calls=r.get('api_calls'), num_turns=r.get('num_turns'),
            agent_seconds=r.get('agent_seconds'), total_wall_seconds=r.get('total_wall_seconds'),
            verifier_seconds=r.get('verifier_seconds'), setup_seconds=r.get('setup_seconds'),
            total_tokens=r.get('total_tokens'), prompt_tokens=r.get('prompt_tokens'),
            completion_tokens=r.get('completion_tokens'),
            cli_total_cost_usd=r.get('cli_total_cost_usd'),
            model=r.get('model'), cli_version=r.get('version'),
            image=r.get('image'), skill_source=r.get('skill_source'),
            discovered_skills=r.get('discovered_skills'),
            study=str(study), result_json=str(rj), trace=trace_path(cell)))
    return out


def load_all(root: Path):
    cells = []
    for task in ORIG10:
        for arm in ARMS:
            st = Path(SRC[(arm, 'orig10')])
            lbl = SRC.get((arm, 'orig10_label'))
            cells += collect(root / st, task, arm, root / st, lbl)
    for task in NEW15:
        for arm in ARMS:
            st = Path(SRC[(arm, 'new15')])
            cells += collect(root / st, task, arm, root / st)
    return cells


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def fmt(x, nd=3):
    return '—' if x is None else f'{x:.{nd}f}'


def report(cells, out: Path, tasks):
    L, A = [], None
    A = L.append
    A('# 25 task × 3 臂：effectiveness 与 efficiency\n')
    A('预算 60 req / 1,000,000 tok / 32,768 out；模型 claude-haiku-4-5-20251001；'
      '同一份 runner 源码（逐字节相同）。\n')
    A('标记：`T` = 被 `api_budget` 截断；`!` = 未评分（agent_error / verifier_error）。\n')

    def sub(cs):
        return {(a): [c for c in cs if c['arm'] == a] for a in ARMS}

    def agg(cs, untrunc_only):
        d = {}
        for a in ARMS:
            rows = [c for c in cs if c['arm'] == a]
            if untrunc_only:
                rows_eff = [c for c in rows if not c['truncated']]
            else:
                rows_eff = rows
            d[a] = dict(mean=mean([c['score'] for c in rows]),
                        n=sum(1 for c in rows if c['score'] is not None),
                        calls=med([c['api_calls'] for c in rows_eff]),
                        secs=med([c['agent_seconds'] for c in rows_eff]),
                        tok=med([c['total_tokens'] for c in rows_eff]),
                        tok_sum=sum(c['total_tokens'] for c in rows_eff if c['total_tokens']),
                        n_eff=sum(1 for c in rows_eff if c['total_tokens'] is not None))
        return d

    A('\n## 1. 逐 task effectiveness\n')
    A('| task | ' + ' | '.join(ARMS) + ' |')
    A('|---|' + '---|' * len(ARMS))
    for t in tasks:
        row = []
        for a in ARMS:
            cs = [c for c in cells if c['task'] == t and c['arm'] == a]
            scored = [c['score'] for c in cs if c['score'] is not None]
            n = len(cs)
            # show the cell count so a partial mean (fewer than 3 trials) is never read
            # as if it were a full task mean
            tag = '' if n == 3 else f' (n={n})'
            row.append(fmt(mean(scored), 3) + tag if scored else (f'—{tag}' if n else '—'))
        A(f'| {t} | ' + ' | '.join(row) + ' |')

    # Only aggregate over tasks that have at least one cell in EVERY arm; otherwise
    # a partial run silently compares different task sets across arms.
    complete = [t for t in tasks
                if all(any(c['task'] == t and c['arm'] == a for c in cells) for a in ARMS)]
    A(f'\n## 2. 汇总（仅含三臂都有数据的 {len(complete)} 个 task）\n')
    # A task can have cells in all three arms yet contribute nothing to the score means
    # (glm-lake-mendota: its test.sh emits no ctrf, so every cell is verifier_error with
    # score=None). Say so explicitly rather than letting the task count imply otherwise.
    unscored = [t for t in complete
                if not any(c['score'] is not None for c in cells if c['task'] == t)]
    if unscored:
        A(f'> 注：**{len(unscored)} 个 task 对下面的 score 均值没有贡献**（全部 cell 无 score）：'
          + '、'.join(f'`{x}`' for x in unscored)
          + '。它们的 token/时间数据仍计入效率列。\n')
        A(f'> 因此 score 均值的实际支撑 task 数为 **{len(complete) - len(unscored)}**。\n')
    for name, ts in ((f'全部 {len(complete)} task', complete),
                     ('剔除 court（验证器缺陷）',
                      [t for t in complete if t not in VERIFIER_DEFECT])):
        cs = [c for c in cells if c['task'] in ts]
        # `mean`/`n` always cover every cell (a truncated run's SCORE is real -- the budget
        # only cut it short afterwards), but the efficiency medians must exclude truncated
        # cells: their token/second counts are artefacts of the 1M-token cap, so including
        # them measures the budget, not the arm. This matches README §3 item 2.
        g = agg(cs, untrunc_only=True)
        A(f'\n**{name}**\n')
        A('> 效率列（calls/seconds/tokens 中位数、n_eff）**只统计未被 `api_budget` 截断的 cell**；'
          '`mean score` 与 `n` 仍覆盖全部 cell。\n')
        A('| arm | mean score | n | calls(med) | seconds(med) | tokens(med) | tokens(sum) | n_eff |')
        A('|---|---|---|---|---|---|---|---|')
        for a in ARMS:
            r = g[a]
            A(f'| {a} | {fmt(r["mean"])} | {r["n"]} | {r["calls"]} | '
              f'{fmt(r["secs"],0)} | {(r["tok"]/1000):.0f}k | {(r["tok_sum"]/1000):.0f}k | {r["n_eff"]} |'
              if r['tok'] else f'| {a} | {fmt(r["mean"])} | {r["n"]} | - | - | - | - | 0 |')
        dd = (g['RepairedSkill']['mean'] or 0) - (g['OriginalSkill']['mean'] or 0)
        dn = (g['RepairedSkill']['mean'] or 0) - (g['NoSkill']['mean'] or 0)
        A(f'\nRepairedSkill − OriginalSkill = **{dd:+.3f}**；'
          f'RepairedSkill − NoSkill = **{dn:+.3f}**；'
          f'token(med) {g["OriginalSkill"]["tok"]} → {g["RepairedSkill"]["tok"]}\n')

    # Some tasks' test.sh emits no ctrf.json, so the harness (by design) discards the
    # shell reward and the cell has no `score`. It still records `raw_reward`, which is a
    # coarser but real signal; report it separately rather than dropping those cells.
    # Split by repair instance. The two batches share the methodology but not the edits
    # (v2 added environment notes; v3 is mostly pure substitution plus one reused repair),
    # so a reader needs to see whether the effect is consistent across both.
    A('\n## 2c. 按修复实例分批（v2 = 原 10，v3 = 新 15）\n')
    for label, ts in (('原 10 个（fixed_skills_v2）', [t for t in complete if t in ORIG10]),
                      ('新 15 个（fixed_skills_v3）', [t for t in complete if t in NEW15])):
        if not ts:
            continue
        g = agg([c for c in cells if c['task'] in ts], untrunc_only=True)
        A(f'\n**{label}**（{len(ts)} 个 task）\n')
        A('> 同 §2：效率列只统计未截断 cell。\n')
        A('| arm | mean score | n | calls(med) | seconds(med) | tokens(med) |')
        A('|---|---|---|---|---|---|')
        for a in ARMS:
            r = g[a]
            tks = f'{(r["tok"]/1000):.0f}k' if r['tok'] else '—'
            A(f'| {a} | {fmt(r["mean"])} | {r["n"]} | {r["calls"]} | {fmt(r["secs"],0)} | {tks} |')
        d = (g['RepairedSkill']['mean'] or 0) - (g['OriginalSkill']['mean'] or 0)
        A(f'\nRepairedSkill − OriginalSkill = **{d:+.3f}**\n')

    A('\n## 2b. 无 `score` 但有 `raw_reward` 的 cell（验证器格式受限的 task）\n')
    rr = [c for c in cells if c['score'] is None and c.get('raw_reward') is not None]
    if not rr:
        A('（无）')
    else:
        A('| task | arm | trial | status | raw_reward |')
        A('|---|---|---|---|---|')
        for c in sorted(rr, key=lambda x: (x['task'], x['arm'], x['trial'])):
            A(f"| {c['task']} | {c['arm']} | {c['trial']} | {c['status']} | {c['raw_reward']} |")
        A('')
        A('按 task × 臂汇总（raw_reward 均值，仅这些 cell）：\n')
        A('| task | ' + ' | '.join(ARMS) + ' |')
        A('|---|' + '---|' * len(ARMS))
        for t_ in sorted({c['task'] for c in rr}):
            vals = []
            for a in ARMS:
                xs = [c['raw_reward'] for c in rr if c['task'] == t_ and c['arm'] == a]
                vals.append(fmt(mean(xs), 3) if xs else '—')
            A(f'| {t_} | ' + ' | '.join(vals) + ' |')

    A('\n## 3. 严格配对（同一 task 同一 trial；两臂都 graded 且未截断）\n')
    A('| 口径 | n | Δscore | Δtokens(med) | Δseconds(med) | tokens 更省 |')
    A('|---|---|---|---|---|---|')
    for name, ts in ((f'全部 {len(complete)}', complete),
                     ('剔除 court', [t for t in complete if t not in VERIFIER_DEFECT])):
        for pair in (('OriginalSkill', 'RepairedSkill'), ('NoSkill', 'RepairedSkill')):
            ds, dt, dsec, n = [], [], [], 0
            for t in ts:
                for i in ('r1', 'r2', 'r3'):
                    a = next((c for c in cells if c['task'] == t and c['arm'] == pair[0] and c['trial'] == i), None)
                    b = next((c for c in cells if c['task'] == t and c['arm'] == pair[1] and c['trial'] == i), None)
                    if not a or not b:
                        continue
                    if a['status'] != 'graded' or b['status'] != 'graded':
                        continue
                    if a['truncated'] or b['truncated']:
                        continue
                    n += 1
                    ds.append((b['score'] or 0) - (a['score'] or 0))
                    dt.append((b['total_tokens'] or 0) - (a['total_tokens'] or 0))
                    dsec.append((b['agent_seconds'] or 0) - (a['agent_seconds'] or 0))
            A(f'| {name} · {pair[1]}−{pair[0]} | {n} | {mean(ds):+.3f} | '
              f'{(med(dt) or 0)/1000:+.0f}k | {med(dsec):+.0f}s | '
              f'{sum(1 for x in dt if x<0)}/{n} |')

    # --- 用户明确问过的两个口径：分数持平时 / 两臂都得分时 -------------------
    A('\n## 3b. 分数持平 vs 两臂都得分（把"省摸索"与"干更多活"分开）\n')
    A('两臂逐 cell 相对变化的中位数。`持平` = Δscore==0；`都得分` = 两臂 score 均 >0。\n')
    A('> ⚠️ **这两个子集的 n 很小（十几对），中位数对"哪些 cell 恰好入选"很敏感** ——')
    A('> 例如本轮 `都得分` 的 Δtokens 从 +6.9%（仅旧 10 个时）翻成 −6.1%，')
    A('> 差别只来自新增的 2 对 `exceltable-in-ppt`（都是 1.0→1.0 且更省 token）。')
    A('> **不要把子集的符号变化当结论**；主结论应看 §2 的全量汇总与 §3 的配对总量。\n')
    A('| 子集 | n | Δtokens | Δseconds | Δcalls | tokens 更省 |')
    A('|---|---|---|---|---|---|')
    for label, pick in (
            ('分数持平 (Repaired−Original)', lambda a, b: (a['score'] or 0) == (b['score'] or 0)),
            ('两臂都得分 (Repaired−Original)',
             lambda a, b: (a['score'] or 0) > 0 and (b['score'] or 0) > 0)):
        rt, rs, rc, n = [], [], [], 0
        for t_ in tasks:
            for i in ('r1', 'r2', 'r3'):
                a = next((c for c in cells if c['task'] == t_ and c['arm'] == 'OriginalSkill' and c['trial'] == i), None)
                b = next((c for c in cells if c['task'] == t_ and c['arm'] == 'RepairedSkill' and c['trial'] == i), None)
                if not a or not b or a['status'] != 'graded' or b['status'] != 'graded':
                    continue
                if a['truncated'] or b['truncated'] or not pick(a, b):
                    continue
                if not (a['total_tokens'] and b['total_tokens'] and a['agent_seconds'] and b['agent_seconds']):
                    continue
                n += 1
                rt.append(b['total_tokens'] / a['total_tokens'] - 1)
                rs.append(b['agent_seconds'] / a['agent_seconds'] - 1)
                if a['api_calls']:
                    rc.append(b['api_calls'] / a['api_calls'] - 1)
        if n:
            A(f'| {label} | {n} | {statistics.median(rt):+.1%} | {statistics.median(rs):+.1%} | '
              f'{(statistics.median(rc) if rc else 0):+.1%} | {sum(1 for x in rt if x<0)}/{n} |')
        else:
            A(f'| {label} | 0 | — | — | — | — |')

    A('\n## 4. 数据完整性\n')
    st = defaultdict(int)
    for c in cells:
        st[(c['arm'], c['status'])] += 1
    A('| arm | ' + ' | '.join(sorted({k[1] for k in st})) + ' | 合计 |')
    A('|---|' + '---|' * (len({k[1] for k in st}) + 1))
    for a in ARMS:
        ks = sorted({k[1] for k in st})
        A(f'| {a} | ' + ' | '.join(str(st.get((a, k), 0)) for k in ks) +
          f' | {sum(v for (aa, _), v in st.items() if aa == a)} |')
    miss = [f"{t}/{a}/r{i}" for t in tasks for a in ARMS for i in (1, 2, 3)
            if not any(c['task'] == t and c['arm'] == a and c['trial'] == f'r{i}' for c in cells)]
    A(f'\n缺失 cell：{len(miss)} 个' + (f'（{", ".join(miss[:20])}）' if miss else ''))

    (out / 'summary.md').write_text('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--out', default='experiments/multi25-20260925/dataset')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)
    cells = load_all(root)
    tasks = ORIG10 + NEW15

    fields = ['task', 'arm', 'trial', 'logical_run_id', 'status', 'score', 'raw_reward', 'truncated',
              'budget_stop_reason', 'termination_reason', 'api_calls', 'num_turns',
              'agent_seconds', 'total_wall_seconds', 'verifier_seconds', 'setup_seconds',
              'total_tokens', 'prompt_tokens', 'completion_tokens', 'cli_total_cost_usd',
              'model', 'cli_version', 'image', 'study', 'result_json', 'trace']
    with (out / 'cells.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields + ['discovered_skills'])
        w.writeheader()
        for c in cells:
            row = {k: c.get(k) for k in fields}
            row['discovered_skills'] = ';'.join(c.get('discovered_skills') or [])
            w.writerow(row)
    with (out / 'cells.jsonl').open('w') as fh:
        for c in cells:
            fh.write(json.dumps(c, ensure_ascii=False, default=str) + '\n')

    report(cells, out, tasks)
    manifest = dict(
        cells=len(cells), tasks=len(tasks), arms=ARMS, trials=3,
        planned=len(tasks) * len(ARMS) * 3,
        sources={f'{k[0]}|{k[1]}': v for k, v in SRC.items()},
        per_arm={a: sum(1 for c in cells if c['arm'] == a) for a in ARMS},
        per_task={t: sum(1 for c in cells if c['task'] == t) for t in tasks},
        budget=dict(requests=60, cumulative_tokens=1_000_000, output_tokens=32_768),
        model='claude-haiku-4-5-20251001')
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"cells={len(cells)} planned={manifest['planned']} -> {out}")
    print(json.dumps(manifest['per_arm'], indent=1))


if __name__ == '__main__':
    main()
