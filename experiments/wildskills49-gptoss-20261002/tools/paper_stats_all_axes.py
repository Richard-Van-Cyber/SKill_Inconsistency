#!/usr/bin/env python3
"""Paper statistics for the wildskills three-model study.

Selection rule (identical to final_three_axis.py): trial r1-r3, no placebo/pilot batches, no NoSkill
for blog-search/skill-routing, only cells whose task package matches the task's current version, and
the latest study among those (this removes the version drift found in the older batch12 studies).

Emits:
  * per-axis arm means (scored and ITT), s.d.
  * paired per-task Delta(Fixed-Original): mean, median, s.d., SE, 95% CI (t and bootstrap),
    paired t-test, Wilcoxon signed-rank, Cohen's d_z, improved/tied/worse
  * efficiency per arm: median [IQR] tokens / API calls / turns / agent seconds, truncation rate,
    tokens per point of score
  * paired per-task efficiency deltas with the same tests
  * a LaTeX fragment with both tables

Usage: python3 paper_stats.py <manifest.csv> [outdir]
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import random
import re
import statistics
import sys

MANIFEST = sys.argv[1]
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else '.'
AXES = [('haiku', 'Claude Haiku 4.5'), ('deepseek', 'DeepSeek-Flash'), ('qwen', 'Qwen3.6-35B (local)'),
        # fourth axis added for the gpt-oss:20b run (study wildskills49-gptoss-20261002); the
        # "current task version" filter below is derived from the qwen axis, and the gptoss
        # cells were verified to carry exactly the same task images.
        ('gptoss', 'gpt-oss-20B (local)')]
ARMS = ('NoSkill', 'OriginalSkill', 'FixedSkill')
NOARM = {'blog-search', 'skill-routing'}
random.seed(20261001)


# ---------------------------------------------------------------- statistics helpers
def betacf(a, b, x):
    MAXIT, EPS, FPMIN = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * betacf(a, b, x) / a
    return 1.0 - front * betacf(b, a, 1 - x) / b


def t_pvalue(t, df):
    """two-sided p-value for a t statistic"""
    if df <= 0 or not math.isfinite(t):
        return float('nan')
    return betai(df / 2.0, 0.5, df / (df + t * t))


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def wilcoxon(diffs):
    """two-sided Wilcoxon signed-rank, normal approximation with tie correction (zeros dropped)"""
    d = [x for x in diffs if abs(x) > 1e-12]
    n = len(d)
    if n < 2:
        return float('nan'), float('nan')
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    tie_term = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(d[order[j + 1]]) - abs(d[order[i]])) < 1e-12:
            j += 1
        avg = (i + j + 2) / 2.0            # average rank (1-based)
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        t = j - i + 1
        if t > 1:
            tie_term += t ** 3 - t
        i = j + 1
    w_plus = sum(ranks[i] for i in range(n) if d[i] > 0)
    mu = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie_term / 48.0
    if var <= 0:
        return float('nan'), float('nan')
    z = (w_plus - mu) / math.sqrt(var)
    return z, 2 * norm_sf(abs(z))


def boot_ci(xs, reps=20000):
    n = len(xs)
    if n < 3:
        return float('nan'), float('nan')
    means = []
    for _ in range(reps):
        means.append(sum(xs[random.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return means[int(0.025 * reps)], means[int(0.975 * reps) - 1]


def t_ci(xs):
    n = len(xs)
    if n < 2:
        return float('nan'), float('nan')
    mean = statistics.mean(xs)
    se = statistics.stdev(xs) / math.sqrt(n)
    # t_{0.975, n-1} approximated by the normal quantile for n>=30, else a small table
    tq = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
          10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}.get(n - 1, 2.010)
    return mean - tq * se, mean + tq * se


# ---------------------------------------------------------------- load + select
rows = list(csv.DictReader(open(MANIFEST)))


def num(v):
    return float(v) if v not in ('', None, 'None') else None


def is_aux(r):
    return 'placebo' in r['batch'] or 'pilot' in r['batch']


def study_date(s):
    mm = re.search(r'(\d{8})', s)
    return mm.group(1) if mm else '0'


cur = {}
for r in rows:
    if r['axis'] == 'qwen' and r['image'] and not is_aux(r):
        cur.setdefault(r['task'], set()).add(r['image'])
cur = {t: sorted(v)[0] for t, v in cur.items()}

cells = {}
for ax, _ in AXES:
    best = {}
    for r in rows:
        if r['axis'] != ax or is_aux(r) or r['trial'] not in ('r1', 'r2', 'r3'):
            continue
        k = (r['task'], r['arm'], r['trial'])
        if k[0] in NOARM and k[1] == 'NoSkill':
            continue
        if cur.get(k[0]) and r['image'] != cur[k[0]]:
            continue
        p = best.get(k)
        if p is None or study_date(r['study']) > study_date(p['study']):
            best[k] = r
    cells[ax] = list(best.values())

report = {}
for ax, label in AXES:
    cs = cells[ax]
    rec = {'label': label, 'arms': {}, 'efficiency': {}}
    for arm in ARMS:
        a = [r for r in cs if r['arm'] == arm]
        sc = [num(r['score']) for r in a if r['status'] == 'graded' and num(r['score']) is not None]
        itt = [(num(r['score']) or 0.0) for r in a]
        u = [r for r in a if r['status'] == 'graded' and r['truncated'] != 'True']
        toks = [num(r['total_tokens']) for r in u if num(r['total_tokens'])]
        # guard: statistics.quantiles needs >=2 points, and a partially finished axis (as well as
        # an arm whose cells all failed) can leave this list empty.
        iqr = statistics.quantiles(toks, n=4) if len(toks) > 1 else None
        rec['arms'][arm] = {'n': len(a), 'n_scored': len(sc),
                            'mean': statistics.mean(sc) if sc else None,
                            'sd': statistics.stdev(sc) if len(sc) > 1 else None,
                            'itt': statistics.mean(itt) if itt else 0.0}
        rec['efficiency'][arm] = {
            'tokens': statistics.median(toks) if toks else None,
            'tokens_iqr': (iqr[0], iqr[2]) if iqr else (None, None),
            'calls': statistics.median([num(r['api_calls']) for r in u if num(r['api_calls'])]),
            'turns': statistics.median([num(r['num_turns']) for r in u if num(r['num_turns'])]),
            'secs': statistics.median([num(r['agent_seconds']) for r in u if num(r['agent_seconds'])]),
            'trunc': 100 * sum(1 for r in a if r['truncated'] == 'True') / len(a),
            'total_tokens': sum(num(r['total_tokens']) or 0 for r in a),
            'score_sum': sum(num(r['score']) or 0 for r in a),
        }
    by = collections.defaultdict(dict)
    for r in cs:
        if num(r['score']) is not None:
            by[r['task']].setdefault(r['arm'], []).append(num(r['score']))
    ds = {t: statistics.mean(v['FixedSkill']) - statistics.mean(v['OriginalSkill'])
          for t, v in by.items() if v.get('FixedSkill') and v.get('OriginalSkill')}
    v = list(ds.values())
    n = len(v)
    # A partially finished axis (or one whose arms produced no paired task) cannot be tested;
    # keep the report shape with zeroed statistics instead of raising, so the finalizer always
    # writes a report even if one axis is short.
    if n >= 2:
        mean = statistics.mean(v)
        sd = statistics.stdev(v)
        se = sd / math.sqrt(n)
        t = mean / se
        lo_t, hi_t = t_ci(v)
        lo_b, hi_b = boot_ci(v)
        z, p_w = wilcoxon(v)
        p_t = t_pvalue(t, n - 1)
    else:
        mean = statistics.mean(v) if v else 0.0
        sd = se = t = z = 0.0
        lo_t = hi_t = lo_b = hi_b = mean
        p_w = p_t = 1.0
    rec['paired'] = {'n': n, 'mean': mean, 'median': statistics.median(v) if v else 0.0, 'sd': sd, 'se': se,
                     'ci_t': (lo_t, hi_t), 'ci_boot': (lo_b, hi_b), 't': t, 'p_t': p_t,
                     'z': z, 'p_wilcoxon': p_w, 'dz': (mean / sd if sd else 0.0),
                     'testable': n >= 2,
                     'improved': sum(1 for x in v if x > 1e-9),
                     'tied': sum(1 for x in v if abs(x) <= 1e-9),
                     'worse': sum(1 for x in v if x < -1e-9)}
    # paired efficiency (tokens & agent seconds), Fixed vs Original
    for metric in ('total_tokens', 'agent_seconds'):
        dm = {}
        for r in cs:
            if r['status'] == 'graded' and num(r[metric]) is not None:
                dm.setdefault(r['task'], {}).setdefault(r['arm'], []).append(num(r[metric]))
        dv = [statistics.mean(x['FixedSkill']) - statistics.mean(x['OriginalSkill'])
              for x in dm.values() if x.get('FixedSkill') and x.get('OriginalSkill')]
        if len(dv) > 2:
            mm = statistics.mean(dv)
            ss = statistics.stdev(dv)
            tt = mm / (ss / math.sqrt(len(dv)))
            rec.setdefault('paired_eff', {})[metric] = {
                'n': len(dv), 'mean': mm, 'median': statistics.median(dv),
                'p': t_pvalue(tt, len(dv) - 1), 't': tt,
                'ci_boot': boot_ci(dv),
                'lower_better': sum(1 for x in dv if x < 0),
                'higher': sum(1 for x in dv if x > 0)}
    report[ax] = rec

json.dump(report, open(os.path.join(OUTDIR, 'paper_stats.json'), 'w'), indent=1, default=str)

# ---------------------------------------------------------------- console summary
print('=' * 100)
for ax, label in AXES:
    r = report[ax]
    print(f'--- {label} ({ax})')

    def ff(v, nd=3, suffix=''):
        """Format a possibly-missing statistic (a partially finished axis has None/empty arms)."""
        return '—' if v is None else f'{v:.{nd}f}{suffix}'

    for arm in ARMS:
        a, e = r['arms'][arm], r['efficiency'][arm]
        tok_per_point = (e['total_tokens'] / e['score_sum'] / 1e6) if e['score_sum'] else None
        print(f'   {arm:<14} mean={ff(a["mean"])} (sd={ff(a["sd"])}, n={a["n_scored"]})  ITT={ff(a["itt"])}  '
              f'tokens={ff((e["tokens"] or 0)/1000, 0, "k") if e["tokens"] else "—"}  '
              f'calls={ff(e["calls"], 0)}  turns={ff(e["turns"], 0)}  '
              f'secs={ff(e["secs"], 0)}  trunc={ff(e["trunc"], 0, "%")}  '
              f'tok/point={ff(tok_per_point, 2, "M")}')
    p = r['paired']
    print(f'   Delta(F-O): mean={p["mean"]:+.3f} median={p["median"]:+.3f} sd={p["sd"]:.3f}'
          + ('' if p.get('testable', True) else '  [NOT TESTABLE: <2 paired tasks]') + ' '
          f'95%CI[t]=[{p["ci_t"][0]:+.3f},{p["ci_t"][1]:+.3f}] 95%CI[boot]=[{p["ci_boot"][0]:+.3f},{p["ci_boot"][1]:+.3f}]')
    print(f'                t({p["n"]-1})={p["t"]:.2f} p_t={p["p_t"]:.2e}  Wilcoxon z={p["z"]:.2f} p={p["p_wilcoxon"]:.2e}  '
          f'd_z={p["dz"]:.2f}  improved/tied/worse={p["improved"]}/{p["tied"]}/{p["worse"]}')
    for metric, d in (r.get('paired_eff') or {}).items():
        unit = 'tokens' if metric == 'total_tokens' else 'seconds'
        print(f'   paired {unit:<9} Fixed-Original: mean={d["mean"]:+.0f} median={d["median"]:+.0f} '
              f'95%CI=[{d["ci_boot"][0]:+.0f},{d["ci_boot"][1]:+.0f}] p={d["p"]:.3f} '
              f'cheaper/higher={d["lower_better"]}/{d["higher"]}')
    print()
