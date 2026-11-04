#!/usr/bin/env python3
"""Generate the headline §4 (effectiveness + efficiency) block for FINAL-REPORT.md.

Why this exists: §4.1/§4.2 used to be filled by hand from `dataset/summary.md` while the
run was still moving, so the numbers could (and did) go stale. This script recomputes them
from the same consolidated cells using the *same* definitions as `consolidate25.py` -- it
imports that module rather than re-deriving anything -- and writes `dataset/section4.md`.

The output is pasted verbatim under §4 of FINAL-REPORT.md; it is a generated file.

    python3 analysis_tools/section4.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consolidate25 as C  # noqa: E402

REPAIR_EXPECTED = 'experiments/multi25-20260925/inputs/repair_expected.json'


def skill_edits(root: Path, tasks, fixed_dir: str):
    """task -> sorted relative files whose bytes differ between pristine and the repair.

    Both repair batches were built with some tasks edited and the rest left untouched on
    purpose. The untouched tasks are a *null-repair control*: their RepairedSkill cells
    mount byte-identical skills to their OriginalSkill cells, so any observed
    RepairedSkill-OriginalSkill difference there is run-to-run noise, not a repair effect.
    Deriving that split from the actual bytes (rather than trusting a note) is what makes
    the placebo claim checkable.
    """
    def snap(base: Path):
        return {str(f.relative_to(base)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in base.rglob('*') if f.is_file()}

    edits = {}
    for t in tasks:
        p = root / 'tasks' / t / 'environment' / 'skills'
        a = root / fixed_dir / t / 'environment' / 'skills'
        if not (p.is_dir() and a.is_dir()):
            continue
        sp, sa = snap(p), snap(a)
        changed = sorted(k for k in set(sp) | set(sa) if sp.get(k) != sa.get(k))
        if changed:
            edits[t] = changed
    return edits


def stats(cells, tasks, untrunc_only):
    """Per-arm score mean/n plus efficiency medians, mirroring consolidate25.report.agg."""
    out = {}
    for arm in C.ARMS:
        rows = [c for c in cells if c['task'] in tasks and c['arm'] == arm]
        eff = [c for c in rows if (not c['truncated'])] if untrunc_only else rows
        scored = [c['score'] for c in rows if c['score'] is not None]
        out[arm] = dict(
            mean=C.mean(scored), n=len(scored),
            hit=sum(1 for x in scored if x > 0),
            calls=C.med([c['api_calls'] for c in eff]),
            secs=C.med([c['agent_seconds'] for c in eff]),
            tok=C.med([c['total_tokens'] for c in eff]),
            n_eff=sum(1 for c in eff if c['total_tokens'] is not None))
    return out


def itt(cells, tasks):
    """Intent-to-treat: an unscored cell (agent_error / verifier_error) counts as 0.

    `stats()` divides by the *scored* cells only, so an arm that fails to produce a
    score on some trials can look better purely because the denominator shrank. With
    pass/fail tasks that is exactly backwards: a cell that never scored is a failure.
    This is the conservative headline metric; the scored-only mean is the optimistic one.
    """
    out = {}
    for arm in C.ARMS:
        rows = [c for c in cells if c['task'] in tasks and c['arm'] == arm]
        total = sum(c['score'] or 0 for c in rows)
        out[arm] = dict(total=total, cells=len(rows),
                        rate=(total / len(rows)) if rows else None,
                        # count of cells that scored ANYTHING. Distinct from `total`:
                        # partial-credit tasks (lab-unit-harmonization, dialogue-parser)
                        # make the score sum non-integral, so `total` must never be
                        # printed as if it were a count of successful cells.
                        hits=sum(1 for c in rows if (c['score'] or 0) > 0),
                        scored=sum(1 for c in rows if c['score'] is not None))
    return out


from math import comb


def fisher_two_sided(a, b, c, d):
    """Two-sided Fisher exact p for [[a,b],[c,d]].

    Used only to make the "this rests on a couple of cells" claim concrete. The test's
    independence assumption is violated here (3 trials of the same task are correlated,
    and the same tasks appear in both batches), so the returned p is a *lower bound* on
    the true uncertainty -- it is quoted to show how weak the evidence is, not to claim
    significance.
    """
    n = a + b + c + d
    r, col = a + c, a + b
    if not n or col > n:
        return None

    def p(x):
        return comb(r, x) * comb(n - r, col - x) / comb(n, col)

    obs = p(a)
    return sum(p(x) for x in range(max(0, col - (n - r)), min(r, col) + 1)
               if p(x) <= obs + 1e-12)


def tok_per_call(cells, tasks):
    """Per-arm medians of total tokens and of tokens per API call.

    Tokens-per-call separates "the document made every request heavier" from "the agent
    took more turns": only the former is a direct consequence of the document's size.
    """
    out = {}
    for arm in C.ARMS:
        rows = [c for c in cells if c['task'] in tasks and c['arm'] == arm and not c['truncated']]
        calls = [c['api_calls'] for c in rows if c['api_calls']]
        toks = [c['total_tokens'] for c in rows if c['total_tokens']]
        tpc = [c['total_tokens'] / c['api_calls'] for c in rows
               if c['total_tokens'] and c['api_calls']]
        out[arm] = dict(calls=C.med(calls), tok=C.med(toks), tpc=C.med(tpc))
    return out


def same_score_pair(cells, tasks):
    """Paired Original->Repaired deltas on cells whose score did NOT change.

    Holding the outcome fixed removes the confound "the repaired arm scores more, so it
    legitimately runs longer": whatever is left is the repair's own per-run cost.
    """
    rt, rc, rpc, n = [], [], [], 0
    for t in tasks:
        for i in ('r1', 'r2', 'r3'):
            a = next((c for c in cells if c['task'] == t and c['arm'] == 'OriginalSkill' and c['trial'] == i), None)
            b = next((c for c in cells if c['task'] == t and c['arm'] == 'RepairedSkill' and c['trial'] == i), None)
            if not a or not b or a['status'] != 'graded' or b['status'] != 'graded':
                continue
            if a['truncated'] or b['truncated']:
                continue
            if (a['score'] or 0) != (b['score'] or 0):
                continue
            if not (a['total_tokens'] and b['total_tokens'] and a['api_calls'] and b['api_calls']):
                continue
            n += 1
            rt.append(b['total_tokens'] / a['total_tokens'] - 1)
            rc.append(b['api_calls'] / a['api_calls'] - 1)
            rpc.append((b['total_tokens'] / b['api_calls']) / (a['total_tokens'] / a['api_calls']) - 1)
    return dict(n=n, dtok=C.med(rt), dcalls=C.med(rc), dtpc=C.med(rpc))


def strict_pairs(cells, tasks, left, right):
    """Same task + same trial; both graded and untruncated. Mirrors report() §3."""
    ds, dt, dsec, n = [], [], [], 0
    for t in tasks:
        for i in ('r1', 'r2', 'r3'):
            a = next((c for c in cells if c['task'] == t and c['arm'] == left and c['trial'] == i), None)
            b = next((c for c in cells if c['task'] == t and c['arm'] == right and c['trial'] == i), None)
            if not a or not b or a['status'] != 'graded' or b['status'] != 'graded':
                continue
            if a['truncated'] or b['truncated']:
                continue
            n += 1
            ds.append((b['score'] or 0) - (a['score'] or 0))
            dt.append((b['total_tokens'] or 0) - (a['total_tokens'] or 0))
            dsec.append((b['agent_seconds'] or 0) - (a['agent_seconds'] or 0))
    return dict(n=n, dscore=C.mean(ds), dtok=C.med(dt), dsec=C.med(dsec),
                cheaper=sum(1 for x in dt if x < 0))


def subset_pairs(cells, tasks, left, right, pick):
    """Relative per-cell change medians for a filtered subset (report() §3b)."""
    rt, rs, n = [], [], 0
    for t in tasks:
        for i in ('r1', 'r2', 'r3'):
            a = next((c for c in cells if c['task'] == t and c['arm'] == left and c['trial'] == i), None)
            b = next((c for c in cells if c['task'] == t and c['arm'] == right and c['trial'] == i), None)
            if not a or not b or a['status'] != 'graded' or b['status'] != 'graded':
                continue
            if a['truncated'] or b['truncated'] or not pick(a, b):
                continue
            if not (a['total_tokens'] and b['total_tokens'] and a['agent_seconds'] and b['agent_seconds']):
                continue
            n += 1
            rt.append(b['total_tokens'] / a['total_tokens'] - 1)
            rs.append(b['agent_seconds'] / a['agent_seconds'] - 1)
    return dict(n=n, dtok=(C.med(rt) if rt else None), dsec=(C.med(rs) if rs else None),
                cheaper=sum(1 for x in rt if x < 0))


def pct(x):
    return '—' if x is None else f'{x:+.1%}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--out', default='experiments/multi25-20260925/dataset/section4.md')
    ap.add_argument('--splice', default='experiments/multi25-20260925/analysis/FINAL-REPORT.md',
                    help='markdown file whose AUTO-4 block is replaced; "" to skip')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    cells = C.load_all(root)
    tasks = C.ORIG10 + C.NEW15

    complete = [t for t in tasks
                if all(any(c['task'] == t and c['arm'] == a for c in cells) for a in C.ARMS)]
    nc = [t for t in complete if t not in C.VERIFIER_DEFECT]
    # tasks whose cells can never carry a score (no ctrf) contribute to efficiency only
    unscored = [t for t in complete
                if not any(c['score'] is not None for c in cells if c['task'] == t)]
    scored_tasks = len(complete) - len(unscored)

    L = []
    A = L.append
    done = sum(1 for t in tasks for a in C.ARMS for i in ('r1', 'r2', 'r3')
               if any(c['task'] == t and c['arm'] == a and c['trial'] == i for c in cells))
    A('<!-- GENERATED by analysis_tools/section4.py -- do not hand-edit. -->')
    A('')
    A(f'> 数据快照：{done}/225 cell（三臂齐备的 task：{len(complete)}/25；'
      f'其中 {len(unscored)} 个无 score，score 均值实际支撑 {scored_tasks} 个 task）。')
    if done < 225:
        A(f'> **本文件是过程快照**：剩余 {225 - done} 个 cell 尚未落盘，数字仍会变化。')
    A('')

    # ---------------- 4.1 effectiveness ----------------
    A('### 4.1 Effectiveness')
    A('')
    A('**(a) 保守口径：intent-to-treat**（未评分的 cell —— `agent_error` / `verifier_error` —— '
      '一律按 0 分计入分母）：')
    A('')
    A('| 口径 | NoSkill | OriginalSkill | RepairedSkill | Δ(Rep−Orig) | Δ(Rep−No) |')
    A('|---|---|---|---|---|---|')
    for name, ts in ((f'全部 {len(complete)} task', complete),
                     (f'剔除 court（验证器缺陷），{len(nc)} task', nc)):
        r = itt(cells, ts)
        f = lambda a: f'{r[a]["rate"]:.3f} ({r[a]["hits"]}/{r[a]["cells"]})'  # noqa: E731
        d1 = (r['RepairedSkill']['rate'] or 0) - (r['OriginalSkill']['rate'] or 0)
        d2 = (r['RepairedSkill']['rate'] or 0) - (r['NoSkill']['rate'] or 0)
        A(f'| {name} | {f("NoSkill")} | {f("OriginalSkill")} | {f("RepairedSkill")} | '
          f'**{d1:+.3f}** | **{d2:+.3f}** |')
    A('')
    A('**(b) 乐观口径：只对已评分的 cell 取均值**（即 `summary.md` §2 的口径）：')
    A('')
    A('| 口径 | NoSkill | OriginalSkill | RepairedSkill | Δ(Rep−Orig) | Δ(Rep−No) | 成功 cell 数 No/Orig/Rep |')
    A('|---|---|---|---|---|---|---|')
    g_all = stats(cells, complete, untrunc_only=False)
    g_nc = stats(cells, nc, untrunc_only=False)
    for name, g in ((f'全部 {len(complete)} task', g_all),
                    (f'剔除 court（验证器缺陷），{len(nc)} task', g_nc)):
        d1 = (g['RepairedSkill']['mean'] or 0) - (g['OriginalSkill']['mean'] or 0)
        d2 = (g['RepairedSkill']['mean'] or 0) - (g['NoSkill']['mean'] or 0)
        hits = '/'.join(f'{g[a]["hit"]}/{g[a]["n"]}' for a in C.ARMS)
        A(f'| {name} | {C.fmt(g["NoSkill"]["mean"])} (n={g["NoSkill"]["n"]}) | '
          f'{C.fmt(g["OriginalSkill"]["mean"])} (n={g["OriginalSkill"]["n"]}) | '
          f'{C.fmt(g["RepairedSkill"]["mean"])} (n={g["RepairedSkill"]["n"]}) | '
          f'**{d1:+.3f}** | **{d2:+.3f}** | {hits} |')
    A('')
    A('> `成功 cell 数` = score>0 的 cell 数 / 已评分 cell 数。'
      '**本 benchmark 绝大多数 task 是"全过才给分"，所以均值实际上由极少数 cell 决定** ——')
    A('> 均值变动 0.01 可能只是 1 个 cell 翻面。判断效应时必须同时看这一列，'
      '不要只读均值差。')
    part = sorted({c['task'] for c in cells
                   if c['score'] is not None and 0 < c['score'] < 1})
    if part:
        pnames = '、'.join('`' + x + '`' for x in part)
        A('> ')
        A(f'> ⚠ 例外：{pnames} 是**部分给分**的 task，其 cell 分数可严格介于 0 与 1 之间。'
          '对这些 task，`成功 cell 数` 记的是"拿到任何分"的 cell，**与 score 求和不严格对应**；'
          '均值一律以 score 求和为准，该列只是"是否有 cell 翻面"的粗看指标。')
    if unscored:
        names = '、'.join('`' + x + '`' for x in unscored)
        A('')
        A(f'（无 score 的 task：{names}——其 `test.sh` 不产出 `ctrf.json`，'
          'harness 按设计丢弃 shell reward；见 §2b 的 `raw_reward`。）')

    # per-batch reproducibility of the effect
    A('')
    A('**分修复实例**（ITT 口径；v2 与 v3 共享方法学但不共享编辑，需要看到效应在两批里是否一致）：')
    A('')
    A('| 批次 | NoSkill | OriginalSkill | RepairedSkill | Δ(Rep−Orig) | tokens(med) Orig→Rep |')
    A('|---|---|---|---|---|---|')
    for label, ts in (('v2（原 10）', [t for t in complete if t in C.ORIG10]),
                      ('v3（新 15）', [t for t in complete if t in C.NEW15])):
        if not ts:
            continue
        r = itt(cells, ts)
        g = stats(cells, ts, untrunc_only=False)
        d = (r['RepairedSkill']['rate'] or 0) - (r['OriginalSkill']['rate'] or 0)
        to, tr = g['OriginalSkill']['tok'], g['RepairedSkill']['tok']
        f = lambda a: f'{r[a]["rate"]:.3f} ({r[a]["hits"]}/{r[a]["cells"]})'  # noqa: E731
        A(f'| {label} | {f("NoSkill")} | {f("OriginalSkill")} | {f("RepairedSkill")} | '
          f'**{d:+.3f}** | '
          f'{to/1000:.0f}k → {tr/1000:.0f}k ({pct(tr/to-1) if to and tr else "—"}) |')

    # ---------------- 4.2 efficiency ----------------
    A('')
    A('### 4.2 Efficiency')
    A('')
    A('**(a) 每臂中位数**（仅未被 `api_budget` 截断的 cell，避免把预算截断当成"更省"）：')
    A('')
    A('| 口径 | arm | calls(med) | seconds(med) | tokens(med) | n_eff |')
    A('|---|---|---|---|---|---|')
    g_eff = stats(cells, complete, untrunc_only=True)
    for arm in C.ARMS:
        r = g_eff[arm]
        tks = f'{r["tok"]/1000:.0f}k' if r['tok'] else '—'
        A(f'| 全部 {len(complete)} task | {arm} | {r["calls"]} | {C.fmt(r["secs"],0)} | {tks} | {r["n_eff"]} |')

    A('')
    A('**(b) 严格配对**（同一 task 同一 trial；两臂都 graded 且都未截断）：')
    A('')
    A('| 口径 | 对比 | n | Δscore | Δtokens(med) | Δseconds(med) | tokens 更省 |')
    A('|---|---|---|---|---|---|---|')
    for name, ts in ((f'全部 {len(complete)}', complete), (f'剔除 court {len(nc)}', nc)):
        for left, right in (('OriginalSkill', 'RepairedSkill'), ('NoSkill', 'RepairedSkill')):
            p = strict_pairs(cells, ts, left, right)
            if not p['n']:
                A(f'| {name} | {right}−{left} | 0 | — | — | — | — |')
                continue
            A(f'| {name} | {right}−{left} | {p["n"]} | {C.fmt(p["dscore"],3)} | '
              f'{(p["dtok"] or 0)/1000:+.0f}k | {(p["dsec"] or 0):+.0f}s | {p["cheaper"]}/{p["n"]} |')

    A('')
    A('**(c) 两个子集**（n 小，符号对入选 cell 敏感 —— 只作诊断，不作结论）：')
    A('')
    A('| 子集 | n | Δtokens | Δseconds | tokens 更省 |')
    A('|---|---|---|---|---|')
    for label, pick in (
            ('分数持平', lambda a, b: (a['score'] or 0) == (b['score'] or 0)),
            ('两臂都得分', lambda a, b: (a['score'] or 0) > 0 and (b['score'] or 0) > 0)):
        p = subset_pairs(cells, tasks, 'OriginalSkill', 'RepairedSkill', pick)
        A(f'| {label} (Rep−Orig) | {p["n"]} | {pct(p["dtok"])} | {pct(p["dsec"])} | '
          f'{p["cheaper"]}/{p["n"]} |')

    A('')
    A('**(d) 原则 1 的直接核查**：修复不得使 **token 开销**或 **fail 比例**上升。'
      'fail 率用 ITT（未评分按失败计），token 用未截断 cell 的中位数：')
    A('')
    A('| 口径 | fail 率 Orig→Rep | Δfail | tokens(med) Orig→Rep | Δtokens | 结论 |')
    A('|---|---|---|---|---|---|')
    for name, ts in ((f'全部 {len(complete)} task', complete),
                     (f'剔除 court {len(nc)}', nc),
                     ('v2（原 10）', [t for t in complete if t in C.ORIG10]),
                     ('v3（新 15）', [t for t in complete if t in C.NEW15])):
        if not ts:
            continue
        r = itt(cells, ts)
        g = stats(cells, ts, untrunc_only=True)
        fo = 1 - (r['OriginalSkill']['rate'] or 0)
        fr = 1 - (r['RepairedSkill']['rate'] or 0)
        to, tr = g['OriginalSkill']['tok'], g['RepairedSkill']['tok']
        dpct = (tr / to - 1) if to and tr else None
        # "no worse" needs both clauses to hold; a direction within noise still gets
        # flagged rather than silently declared a pass
        if (fr - fo) <= 0 and (dpct is None or dpct <= 0):
            verdict = '通过'
        elif (fr - fo) <= 0.02 and (dpct is not None and dpct <= 0.05):
            verdict = f'边缘（Δfail {fr-fo:+.3f}, Δtok {pct(dpct)}）'
        else:
            verdict = '**不通过**'
        A(f'| {name} | {fo:.1%} → {fr:.1%} | {fr-fo:+.1%} | '
          f'{to/1000:.0f}k → {tr/1000:.0f}k | {pct(dpct)} | {verdict} |')
    A('')
    A('> "通过"只表示**没有观察到变差**，不等于修复有效 —— 有效性见 §4.1（未被确立）。')

    A('')
    A('**(e) token 增量从哪来：更多轮次，还是每次调用更重？**')
    A('')
    A('`tokens(med)` 是**总量**，它同时受"跑了多少轮"和"每轮多大"影响。'
      '把两者拆开才能判断修复是否让**上下文变重**（文档变长的直接后果）：')
    A('')
    A('| 口径 | arm | calls(med) | tokens(med) | **tokens/call(med)** |')
    A('|---|---|---|---|---|')
    for name, ts in ((f'全部 {len(complete)} task', complete),
                     ('v2（原 10）', [t for t in complete if t in C.ORIG10]),
                     ('v3（新 15）', [t for t in complete if t in C.NEW15])):
        if not ts:
            continue
        e = tok_per_call(cells, ts)
        for arm in C.ARMS:
            r = e[arm]
            A(f'| {name} | {arm} | {r["calls"]} | '
              f'{(r["tok"]/1000):.0f}k | {(r["tpc"]/1000):.1f}k |' if r['tpc'] else
              f'| {name} | {arm} | - | - | - |')
    eo = tok_per_call(cells, complete)
    A('')
    A('同一 task 同一 trial、且**两臂得分相同**的配对（分数不变 ⇒ 没有"修好之后多干活"的混淆，'
      '最能反映修复本身的代价）：')
    A('')
    pair = same_score_pair(cells, tasks)
    A(f'- n = **{pair["n"]}** 对；Δcalls 中位数 = **{pct(pair["dcalls"])}**；'
      f'Δ(tokens/call) 中位数 = **{pct(pair["dtpc"])}**；'
      f'Δtokens 中位数 = **{pct(pair["dtok"])}**。')
    A('')
    A('**读法**：若 Δ(tokens/call) ≈ 0 而 Δcalls > 0，'
      '则总 token 上升**不是**"文档变长把每次请求撑大"造成的，'
      '而是模型**多跑了几轮**。这两者的代价含义完全不同：'
      '前者是修复引入的上下文税（应当避免），后者是行为变化（应当用轮次预算去管）。')
    A('')
    A(f'> ⚠ 该配对子集的 n 只有 {pair["n"]}，且"分数持平"这一条件本身会筛选 cell，'
      '符号对小样本敏感 —— 结论要结合 (e) 上半表的逐臂 tokens/call 一起读，不要只看一个数。')

    # ------------- 4.1b the null-repair controls (placebo) -------------
    edits3 = skill_edits(root, C.NEW15, 'fixed_skills_v3')
    edits2 = skill_edits(root, C.ORIG10, 'fixed_skills_v2')
    edited3 = set(edits3)
    null3 = [t for t in C.NEW15 if t not in edited3]
    edited2 = set(edits2)
    null2 = [t for t in C.ORIG10 if t not in edited2]
    exp_path = root / REPAIR_EXPECTED
    warn = ''
    if exp_path.exists():
        exp = {k.split('/')[0] for k in json.loads(exp_path.read_text())}
        if exp != edited3:
            warn = (f'⚠ `repair_expected.json` 声明编辑 {sorted(exp)}，'
                    f'但按字节比对实际为 {sorted(edited3)} —— 两者不一致，需先查明。')
    A('')
    A('### 4.1b 零编辑对照（安慰剂检验）')
    A('')
    A(f'按字节比对 `tasks/` 与两批修复目录：'
      f'**v2 有编辑 {len(edited2)} 个 / 零编辑 {len(null2)} 个 task**；'
      f'**v3 有编辑 {len(edited3)} 个（{sum(len(v) for v in edits3.values())} 个文件）/ '
      f'零编辑 {len(null3)} 个 task**。')
    if warn:
        A('')
        A(warn)
    A('')
    A('零编辑 task 的 RepairedSkill 挂载的技能与 OriginalSkill **完全相同**，'
      '所以两者的分数差只能是 n=3 的运行噪声 —— 它给出本实验**噪声下限**的实测值：')
    A('')
    A('| 批次 | 子集 | task 数 | NoSkill | OriginalSkill | RepairedSkill | Δ(Rep−Orig) | 成功 cell 差 |')
    A('|---|---|---|---|---|---|---|---|')
    deltas = {}
    cellsmap = {}
    for batch, edited_, null_ in (('v2', edited2, null2), ('v3', edited3, null3)):
        for key, label, ts in (('edited', '有编辑', [t for t in sorted(edited_) if t in complete]),
                               ('null', '零编辑对照（安慰剂）', [t for t in null_ if t in complete])):
            if not ts:
                A(f'| {batch} | {label} | 0 | — | — | — | — | — |')
                continue
            r = itt(cells, ts)
            f = lambda a: f'{r[a]["rate"]:.3f} ({r[a]["hits"]}/{r[a]["cells"]})'  # noqa: E731
            d = (r['RepairedSkill']['rate'] or 0) - (r['OriginalSkill']['rate'] or 0)
            dcells = r['RepairedSkill']['hits'] - r['OriginalSkill']['hits']
            deltas[(batch, key)] = dcells
            cellsmap[(batch, key)] = (r['RepairedSkill'], r['OriginalSkill'], len(ts))
            A(f'| {batch} | {label} | {len(ts)} | {f("NoSkill")} | {f("OriginalSkill")} | '
              f'{f("RepairedSkill")} | **{d:+.3f}** | {dcells:+.0f} |')
    A('')
    A('> 读法：安慰剂组的 |Δ| 就是"什么都没有修"时能观察到的量级。'
      '若某批的 Δ 并不明显大于同批安慰剂组的 |Δ|，就不能把该批的增益归因于修复。'
      '两组的 task 组成不同（难度不可互换），因此对照给出的是**噪声下限的量级指示**，'
      '而不是严格的原假设分布；task 数少时尤其不要过度解读。')
    A('> ')
    A('> 括号里是 `成功 cell 数 / 总 cell 数`（ITT 分子分母）。'
      '**本 benchmark 多为一票否决的二元判定，真正要看的是最后一列的分子差，而不是均值** ——'
      f'例如 v2 有编辑组全组效应 = **{deltas.get(("v2","edited"), 0):+.0f} 个 cell**，'
      f'而 v2 安慰剂组自身就漂移了 **{deltas.get(("v2","null"), 0):+.0f} 个 cell**；'
      f'v3 有编辑组 = **{deltas.get(("v3","edited"), 0):+.0f} 个 cell**，'
      f'v3 安慰剂组 = **{deltas.get(("v3","null"), 0):+.0f} 个 cell**。')
    A('')
    A('**这批证据有多弱**：把"有编辑组"的 RepairedSkill 与 OriginalSkill 做成 2×2 列联表，')
    A('用 Fisher 精确检验（最宽松的 cell 级口径）：')
    A('')
    A('| 批次 | Repaired 成功/总数 | Original 成功/总数 | Fisher 双侧 p |')
    A('|---|---|---|---|')
    for batch in ('v2', 'v3'):
        got = cellsmap.get((batch, 'edited'))
        if not got:
            continue
        rp, ro, nt = got
        a, b = rp['hits'], rp['cells'] - rp['hits']
        c, d_ = ro['hits'], ro['cells'] - ro['hits']
        p = fisher_two_sided(a, b, c, d_)
        A(f'| {batch}（{nt} task） | {a}/{rp["cells"]} | {c}/{ro["cells"]} | '
          f'{"—" if p is None else f"{p:.2f}"} |')
    A('')
    A('> ⚠ 该 p 值**高估了显著性**：同一 task 的 3 个 trial 不独立（相关性使有效样本量更小），')
    A('> 且未做多重比较校正。列出它只为说明**证据有多弱**，不是要主张显著。')

    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    body = '\n'.join(L) + '\n'
    out.write_text(body)
    print(f'[{done}/225 cells] wrote {out.relative_to(root)}')

    if args.splice:
        target = root / args.splice
        begin, end = '<!-- BEGIN AUTO-4', '<!-- END AUTO-4 -->'
        text = target.read_text()
        bi = text.find(begin)
        ei = text.find(end)
        if bi < 0 or ei < 0 or ei < bi:
            raise SystemExit(f'ERROR: markers not found in {target}; refusing to splice '
                             f'(begin={bi}, end={ei}). Add "{begin} ... -->" and "{end}".')
        head = text[:text.index('\n', bi) + 1]
        target.write_text(f'{head}\n{body}\n{text[ei:]}')
        print(f'  spliced into {target.relative_to(root)}')


if __name__ == '__main__':
    main()
