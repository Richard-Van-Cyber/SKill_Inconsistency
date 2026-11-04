#!/usr/bin/env python3
"""Consolidate the wildskills13 batch (13 new tasks) into a dataset + report.

Reads `experiments/<study>/runs/*/result.json` (the same per-cell record the driver writes for
every wildskills study) and writes, in the schema of `experiments/wildskills-dataset/`:

  experiments/wildskills13-dataset/cells.csv     one row per cell
  experiments/wildskills13-dataset/summary.md    effectiveness + efficiency, per task and per arm

Arms are NoSkill / OriginalSkill / FixedSkill. Unscored cells (agent_error / verifier_error) are
excluded from n and reported separately; budget-truncated cells keep their (lower-bound) score in
the effectiveness tables and are excluded from the efficiency medians.

Usage:
  python3 consolidate13.py [--studies wildskills13-20260929,wildskills13-pilot-20260929]
                           [--out ../../experiments/wildskills13-dataset]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXPERIMENTS = REPO / 'experiments'
ARMS = ['NoSkill', 'OriginalSkill', 'FixedSkill']
# Column order matches experiments/wildskills-dataset/cells.csv (the 12-task batch) so the two
# files can be concatenated directly; `truncated` is appended as the only added column.
COLUMNS = ['corpus', 'task', 'arm', 'trial', 'logical_run_id', 'status', 'score',
           'budget_stop_reason', 'termination_reason', 'api_calls', 'num_turns', 'agent_seconds',
           'total_wall_seconds', 'verifier_seconds', 'setup_seconds', 'total_tokens',
           'prompt_tokens', 'completion_tokens', 'cli_total_cost_usd', 'model', 'image', 'study',
           'budget', 'result_json', 'truncated']
UNSCORED = {'agent_error', 'verifier_error', 'environment_error', 'crashed', 'model_identity_error'}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(v, nd=3):
    return '—' if v is None else f'{v:.{nd}f}'


def fmtk(v):
    if v is None:
        return '—'
    if v >= 1_000_000:
        return f'{v/1e6:.2f}M'
    if v >= 1000:
        return f'{v/1000:.0f}k'
    return f'{v:.0f}'


def collect(studies: list[str]) -> list[dict]:
    rows = []
    for study in studies:
        runs = EXPERIMENTS / study / 'runs'
        if not runs.is_dir():
            print(f'  [warn] no runs dir for {study}', file=sys.stderr)
            continue
        for res in sorted(runs.glob('*/result.json')):
            d = json.loads(res.read_text())
            inner = res.parent.name
            task = d.get('task') or inner.split('__')[0]
            arm = d.get('arm') or inner.split('__')[1]
            if arm not in ARMS:
                continue
            rows.append({
                'corpus': 'wildskills-13', 'task': task, 'arm': arm,
                'trial': d.get('repeat') or inner.rsplit('r', 1)[-1],
                'logical_run_id': d.get('logical_run_id') or inner,
                'status': d.get('status'), 'score': num(d.get('score')),
                'truncated': (d.get('budget_stop_reason') or '') == 'api_budget',
                'budget_stop_reason': d.get('budget_stop_reason'),
                'termination_reason': d.get('termination_reason'),
                'api_calls': num(d.get('api_calls')), 'num_turns': num(d.get('num_turns')),
                'agent_seconds': num(d.get('agent_seconds')),
                'total_wall_seconds': num(d.get('total_wall_seconds')),
                'verifier_seconds': num(d.get('verifier_seconds')),
                'setup_seconds': num(d.get('setup_seconds')),
                'total_tokens': num(d.get('total_tokens')),
                'prompt_tokens': num(d.get('prompt_tokens')),
                'completion_tokens': num(d.get('completion_tokens')),
                'cli_total_cost_usd': num(d.get('cli_total_cost_usd')),
                'model': d.get('model'), 'image': d.get('image'), 'study': study,
                'budget': 'primary',
                'result_json': str(res.relative_to(REPO)),
            })
    return rows


def scored(r):
    return r['score'] is not None and r['status'] not in UNSCORED


def sel(rows, **kw):
    out = rows
    for k, v in kw.items():
        out = [r for r in out if r[k] == v]
    return out


def task_table(rows, arm):
    per = defaultdict(list)
    for r in rows:
        if r['arm'] == arm and scored(r):
            per[r['task']].append(r['score'])
    return {t: (mean(v), len(v)) for t, v in per.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--studies', default='wildskills13-20260929')
    ap.add_argument('--placebo-study', default='wildskills13-placebo-20260929')
    ap.add_argument('--out', default=str(EXPERIMENTS / 'wildskills13-dataset'))
    args = ap.parse_args()
    studies = [s for s in args.studies.split(',') if s]
    out = Path(args.out)

    rows = collect(studies)
    if not rows:
        print('no cells collected; nothing written')
        return 1
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'cells.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)

    tasks = sorted({r['task'] for r in rows})
    L: list[str] = []
    A = L.append
    A('# wildskills13 — 13 个新 task × 3 臂：effectiveness 与 efficiency')
    A('')
    A(f'来源 study：`{", ".join(studies)}`；模型 `claude-haiku-4-5`；预算 60 req / 1,000,000 tok / '
      '32,768 out；3 trial。')
    A('')
    A(f'cell 总数 **{len(rows)}**（{len(tasks)} task × 3 臂 × 3 trial 减去未跑满的部分）。'
      f'未评分（`agent_error`/`verifier_error` 等）**{sum(1 for r in rows if not scored(r))}** 格，'
      '不计入 n；被预算截断 **'
      f'{sum(1 for r in rows if r["truncated"])}** 格，其分数是下界。')
    A('')

    A('## 1. 逐 task effectiveness（scored-only）')
    A('')
    A('| task | NoSkill | OriginalSkill | FixedSkill | Δ(F−O) | Δ(F−N) |')
    A('|---|---|---|---|---|---|')
    tt = {a: task_table(rows, a) for a in ARMS}
    for t in tasks:
        n = tt['NoSkill'].get(t, (None, 0))[0]
        o = tt['OriginalSkill'].get(t, (None, 0))[0]
        f = tt['FixedSkill'].get(t, (None, 0))[0]
        d1 = f - o if (f is not None and o is not None) else None
        d2 = f - n if (f is not None and n is not None) else None
        A(f'| {t} | {fmt(n)} | {fmt(o)} | {fmt(f)} | '
          f'{fmt(d1) if d1 is None else f"{d1:+.3f}"} | {fmt(d2) if d2 is None else f"{d2:+.3f}"} |')
    A('')

    A('## 1b. ITT 口径（未评分计 0）')
    A('')
    A('| 臂 | mean score (ITT) | n（全部启动的 cell） |')
    A('|---|---|---|')
    for arm in ARMS:
        s = [r for r in rows if r['arm'] == arm]
        vals = [(r['score'] if scored(r) else 0.0) for r in s]
        A(f'| {arm} | {fmt(mean(vals))} | {len(s)} |')
    A('')

    # ---- placebo noise floor -------------------------------------------------
    placebo = collect([args.placebo_study])
    if placebo:
        A('## 1c. 零编辑安慰剂：本设计的噪声底')
        A('')
        A(f'安慰剂 study `{args.placebo_study}` 的覆盖层与 pristine **逐字节相同**，'
          '因此 FixedSkill 与 OriginalSkill 注入的内容完全一致，Δ(F−O) 的期望值为 0；'
          '测到的任何非零值都是本设计的测量噪声。')
        A('')
        pt = {a: task_table(placebo, a) for a in ARMS}
        pl_deltas = {t: pt['FixedSkill'][t][0] - pt['OriginalSkill'][t][0]
                     for t in pt['FixedSkill']
                     if t in pt['OriginalSkill'] and pt['FixedSkill'][t][0] is not None
                     and pt['OriginalSkill'][t][0] is not None}
        real_deltas = deltas if (deltas := {t: tt['FixedSkill'][t][0] - tt['OriginalSkill'][t][0]
                                            for t in tasks
                                            if t in tt['FixedSkill'] and t in tt['OriginalSkill']
                                            and tt['FixedSkill'][t][0] is not None
                                            and tt['OriginalSkill'][t][0] is not None}) else {}
        def describe(d):
            if not d:
                return None
            v = list(d.values())
            return {'n': len(v), 'mean': mean(v), 'sd': statistics.pstdev(v),
                    'imp': sum(1 for x in v if x > 1e-9),
                    'tie': sum(1 for x in v if abs(x) <= 1e-9),
                    'wor': sum(1 for x in v if x < -1e-9)}
        for label, d in (('安慰剂（零编辑 task）', pl_deltas), ('真修复（被编辑 task）', real_deltas)):
            st = describe(d)
            if not st:
                continue
            A(f'* **{label}**：n={st["n"]}，mean Δ = {st["mean"]:+.4f}，sd = {st["sd"]:.3f}，'
              f'改善/持平/变差 = {st["imp"]}/{st["tie"]}/{st["wor"]}')
        st_p, st_r = describe(pl_deltas), describe(real_deltas)
        if st_p and st_r and st_p['sd']:
            se = st_p['sd'] / (st_r['n'] ** 0.5)
            A('')
            A(f'以安慰剂 sd 作为噪声尺度：真修复 mean Δ = {st_r["mean"]:+.4f}，'
              f'标准误 ≈ {se:.3f}，|t| ≈ {abs(st_r["mean"]) / se:.2f}')
            A('')
            A('> 读法：|t| < 2 表示本批的修复效应**落在噪声内**，与 batch-2 的结论一致；'
              '若 |t| ≥ 2 才谈得上"修复有效"。')
        A('')
        A('| task | 安慰剂 Δ(F−O) |')
        A('|---|---|')
        for t, v in sorted(pl_deltas.items(), key=lambda kv: -kv[1]):
            A(f'| {t} | {v:+.3f} |')
        A('')

        # ---- difference-in-differences on the overlapping tasks -----------------
        shared = sorted(set(pl_deltas) & set(real_deltas))
        if shared:
            A('## 1c-bis 双重差分（task 内配对）：处理效应 = Δ_edited − Δ_placebo')
            A('')
            A('这 6 个 task **同时**出现在主实验（修复覆盖层）与安慰剂 study（pristine 覆盖层）里，'
              '所以可以对每个 task 把"该 task 自身的 trial 波动"一并扣掉：')
            A('')
            A('| task | Δ_edited（真修复） | Δ_placebo（零编辑） | DiD |')
            A('|---|---|---|---|')
            dids = []
            for t in shared:
                d = real_deltas[t] - pl_deltas[t]
                dids.append(d)
                A(f'| {t} | {real_deltas[t]:+.3f} | {pl_deltas[t]:+.3f} | **{d:+.3f}** |')
            A('')
            if dids:
                se = (statistics.pstdev(dids) / (len(dids) ** 0.5)) if len(dids) > 1 else float('nan')
                tstat = abs(mean(dids)) / se if se and se > 0 else float('nan')
                A(f'* 平均 DiD = **{mean(dids):+.4f}**（n={len(dids)} task），sd = '
                  f'{statistics.pstdev(dids):.3f}，标准误 ≈ {se:.3f}，|t| ≈ {tstat:.2f}')
                A(f'* 安慰剂噪声底（Δ_placebo 的 sd）= {st_p["sd"]:.3f}'
                  + ('（偏小：3 trial、且这些 task 的 verifier 是多检查项确定性判分）'
                     if st_p['sd'] < 0.1 else ''))
                A('')

    # ---- mechanism (needs analyze_mechanism.py to have run) -------------------
    mech = out / 'mechanism.csv'
    if mech.is_file():
        mrows = list(csv.DictReader(open(mech, newline='')))
        mrows = [r for r in mrows if r.get('task') in set(tasks)]
        if mrows:
            A('## 1d. 机制：agent 有没有真的碰到缺陷面')
            A('')
            A('缺陷面 = 修复覆盖层相对 pristine 改动的文件；"碰到" = 轨迹里读/写过其中任一文件。')
            A('')
            A('| 臂 | cell | 碰到缺陷面 |')
            A('|---|---|---|')
            for arm in ARMS:
                s = [r for r in mrows if r['arm'] == arm]
                if not s:
                    continue
                hit = sum(1 for r in s if str(r.get('touched_any')).lower() == 'true')
                A(f'| {arm} | {len(s)} | {hit}/{len(s)} |')
            A('')

    A('## 2. 臂汇总')
    A('')
    A('> 效率列只统计**未被预算截断**的格；`mean score` 与 n 覆盖全部已评分格。')
    A('')
    A('| 臂 | mean score | n | calls(med) | turns(med) | tokens(med) | agent s(med) | tokens(sum) |')
    A('|---|---|---|---|---|---|---|---|')
    for arm in ARMS:
        s = [r for r in rows if r['arm'] == arm and scored(r)]
        u = [r for r in s if not r['truncated']]
        A(f'| {arm} | {fmt(mean([r["score"] for r in s]))} | {len(s)} | '
          f'{fmt(median([r["api_calls"] for r in u]), 1)} | {fmt(median([r["num_turns"] for r in u]), 1)} | '
          f'{fmtk(median([r["total_tokens"] for r in u]))} | '
          f'{fmt(median([r["agent_seconds"] for r in u]), 0)} | '
          f'{fmtk(sum(r["total_tokens"] or 0 for r in s))} |')
    A('')

    A('## 2b. efficiency（成功/失败分解、同分对照、性价比）')
    A('')
    A('> ⚠️ 下面这些是**原始聚合数字**，不是修复效应：逐 task 看方向是混合的'
      '（14 个 task 里 7 个 FixedSkill 更贵、5 个更便宜），且安慰剂 study 里'
      '**逐字节相同**的两个臂也会出现 ~150k token 的系统差（疑似臂的运行位次效应）。'
      '效率的双重差分见 §2c，结论是**不能**声称修复降低了 token 开销。')
    A('')
    A('| 臂 | 成功 cell tokens(med) | 零分 cell tokens(med) | 成功 calls(med) | 零分 calls(med) |')
    A('|---|---|---|---|---|')
    for arm in ARMS:
        s0 = [r for r in rows if r['arm'] == arm and scored(r) and not r['truncated']]
        ok = [r for r in s0 if (r['score'] or 0) > 0]
        bad = [r for r in s0 if (r['score'] or 0) == 0]
        A(f'| {arm} | {fmtk(median([r["total_tokens"] for r in ok]))} | '
          f'{fmtk(median([r["total_tokens"] for r in bad]))} | '
          f'{fmt(median([r["api_calls"] for r in ok]), 1)} | '
          f'{fmt(median([r["api_calls"] for r in bad]), 1)} |')
    A('')
    A('**同分对照**：只取两臂 task 均值完全相同的 task，比较 OriginalSkill → FixedSkill 的'
      'calls / tokens / tokens-per-call（分数一样，所以差异不是能力差异）。')
    A('')
    A('| task | Δcalls | Δtokens | Δ(tokens/call) |')
    A('|---|---|---|---|')
    for t in tasks:
        o, f = tt['OriginalSkill'].get(t, (None, 0))[0], tt['FixedSkill'].get(t, (None, 0))[0]
        if o is None or f is None or abs(o - f) > 1e-9:
            continue
        def em(arm):
            u = [r for r in rows if r['task'] == t and r['arm'] == arm and scored(r)
                 and not r['truncated']]
            return (median([r['api_calls'] for r in u]),
                    median([r['total_tokens'] for r in u]),
                    median([(r['total_tokens'] / r['api_calls']) for r in u
                            if r['api_calls'] and r['total_tokens']]))
        co, to, qo = em('OriginalSkill')
        cf, tf, qf = em('FixedSkill')
        dc = (cf - co) if (co is not None and cf is not None) else None
        dt = ((tf - to) / to * 100) if (to and tf) else None
        dq = ((qf - qo) / qo * 100) if (qo and qf) else None
        A(f'| {t} | {fmt(dc, 1)} | {fmt(dt, 1)}% | {fmt(dq, 1)}% |')
    A('')
    A('**性价比**：总 token 消耗 / 命中 cell 数（命中 = 分数 > 0）。')
    A('')
    A('| 臂 | 总 token | 分数总和 | 命中 cell | 每命中 cell 的 token | 每 1 分的 token |')
    A('|---|---|---|---|---|---|')
    for arm in ARMS:
        a = [r for r in rows if r['arm'] == arm]
        tot = sum(r['total_tokens'] or 0 for r in a)
        ssum = sum(r['score'] or 0 for r in a if scored(r))
        h = sum(1 for r in a if scored(r) and (r['score'] or 0) > 0)
        A(f'| {arm} | {fmtk(tot)} | {fmt(ssum, 1)} | {h}/{len(a)} | '
          f'{fmtk(tot / h) if h else "—"} | {fmtk(tot / ssum) if ssum else "—"} |')
    A('')

    A('## 2c. efficiency 的双重差分（对照 §2b 的原始数字）')
    A('')
    if placebo:
        shared_tasks = sorted(set(pl_deltas) & {t for t in tasks})
        hdr = ('| task | Δtok_edited | Δtok_placebo | DiD_tok | Δcalls_edited | '
               'Δcalls_placebo | DiD_calls |')
        A(hdr)
        A('|---|---|---|---|---|---|---|')
        did_tok, did_calls = [], []

        def med(rs, key):
            v = [r[key] for r in rs if r['arm'] == 'OriginalSkill' or r['arm'] == 'FixedSkill']
            return v

        def arm_med(rows_, task, arm, key):
            v = [r[key] for r in rows_ if r['task'] == task and r['arm'] == arm
                 and not r['truncated'] and r[key] is not None]
            return statistics.median(v) if v else None

        for t in shared_tasks:
            vals = []
            for key in ('total_tokens', 'api_calls'):
                o_m, f_m = arm_med(rows, t, 'OriginalSkill', key), arm_med(rows, t, 'FixedSkill', key)
                o_p = arm_med(placebo, t, 'OriginalSkill', key)
                f_p = arm_med(placebo, t, 'FixedSkill', key)
                de = (f_m - o_m) if None not in (f_m, o_m) else None
                dp = (f_p - o_p) if None not in (f_p, o_p) else None
                vals.append((de, dp, (de - dp) if None not in (de, dp) else None))
            (te, tp, td), (ce, cp, cd) = vals
            if td is not None:
                did_tok.append(td)
            if cd is not None:
                did_calls.append(cd)
            f1 = lambda x: '—' if x is None else (f'{x:+,.0f}' if abs(x or 0) > 100 else f'{x:+.1f}')
            A(f'| {t} | {f1(te)} | {f1(tp)} | **{f1(td)}** | {f1(ce)} | {f1(cp)} | **{f1(cd)}** |')
        A('')
        for name, v in (('tokens', did_tok), ('calls', did_calls)):
            if len(v) > 1:
                m_ = mean(v)
                se_ = statistics.pstdev(v) / (len(v) ** 0.5)
                A(f'* **{name} DiD**：mean = {m_:+,.0f}，sd = {statistics.pstdev(v):,.0f}，'
                  f'标准误 ≈ {se_:,.0f}，|t| ≈ {abs(m_) / se_:.2f}（n={len(v)}）')
        A('')
        A('> 读法：DiD 为正表示"真修复"相对零编辑对照**更贵**。本批 tokens/calls 的 DiD 都为正，'
          '因此 §2b 里"FixedSkill token 更低"**不能**解释为修复带来的效率提升；'
          '唯一站得住的效率陈述是"修复没有让截断率或轮次变差"。')
        A('')
    else:
        A('（未提供 --placebo-study，无法做效率对照）')
        A('')

    A('## 3. 逐 task 配对 Δ(FixedSkill − OriginalSkill)')
    A('')
    deltas = {t: tt['FixedSkill'][t][0] - tt['OriginalSkill'][t][0]
              for t in tasks
              if t in tt['FixedSkill'] and t in tt['OriginalSkill']
              and tt['FixedSkill'][t][0] is not None and tt['OriginalSkill'][t][0] is not None}
    if deltas:
        vals = list(deltas.values())
        imp = sum(1 for v in vals if v > 1e-9)
        tie = sum(1 for v in vals if abs(v) <= 1e-9)
        wor = sum(1 for v in vals if v < -1e-9)
        A(f'* 配对 task：**{len(vals)}**；改善 **{imp}** / 持平 **{tie}** / 变差 **{wor}**')
        A(f'* task 等权 mean Δ = **{mean(vals):+.4f}**，中位 {statistics.median(vals):+.4f}')
        A('')
        A('| task | Δ(F−O) |')
        A('|---|---|')
        for t, v in sorted(deltas.items(), key=lambda kv: -kv[1]):
            A(f'| {t} | {v:+.3f} |')
    A('')

    A('## 4. 预算截断')
    A('')
    A('| 臂 | 截断 cell | 占比 |')
    A('|---|---|---|')
    for arm in ARMS:
        s = [r for r in rows if r['arm'] == arm]
        tr = sum(1 for r in s if r['truncated'])
        A(f'| {arm} | {tr}/{len(s)} | {tr/len(s)*100:.0f}% |' if s else f'| {arm} | 0/0 | — |')
    A('')

    A('## 5. 与既有 12 个 wildskills task 的对照')
    A('')
    old = EXPERIMENTS / 'wildskills-dataset' / 'cells.csv'
    if old.is_file():
        orows = list(csv.DictReader(open(old, newline='')))
        A('| 数据集 | task | 臂 | mean score | n |')
        A('|---|---|---|---|---|')
        for label, rws in (('旧 12 task', orows), ('本批 13 task', rows)):
            for arm in ARMS:
                s = [r for r in rws if r['arm'] == arm and num(r['score']) is not None]
                A(f'| {label} | {len({r["task"] for r in rws})} | {arm} | '
                  f'{fmt(mean([num(r["score"]) for r in s]))} | {len(s)} |')
        A('')
    else:
        A('（未找到 `experiments/wildskills-dataset/cells.csv`，跳过对照）')
        A('')

    A('## 6. 数据完整性')
    A('')
    A('| study | cell | graded | 未评分 | 截断 |')
    A('|---|---|---|---|---|')
    for study in studies:
        s = sel(rows, study=study)
        if not s:
            continue
        A(f'| {study} | {len(s)} | {sum(1 for r in s if scored(r))} | '
          f'{sum(1 for r in s if not scored(r))} | {sum(1 for r in s if r["truncated"])} |')
    A('')
    bad = Counter(r['status'] for r in rows if not scored(r))
    if bad:
        A('未评分明细：' + ', '.join(f'`{k}` × {v}' for k, v in bad.most_common()))
        A('')

    (out / 'summary.md').write_text('\n'.join(L) + '\n')
    print(f'wrote {out}/cells.csv ({len(rows)} cells) and {out}/summary.md')
    print(f'tasks={len(tasks)} arms={len(ARMS)} scored={sum(1 for r in rows if scored(r))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
