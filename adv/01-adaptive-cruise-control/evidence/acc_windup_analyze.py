#!/usr/bin/env python3
"""Analyse the ACC anti-windup paired runs.

pid-controller/SKILL.md's copy-paste PIDController integrates unconditionally and
then advertises three anti-windup schemes in a section that implements none of
them. The task forces saturation (0 -> 27 m/s under |a| <= 3.0 m/s^2), so the
integral winds up and the verifier's speed metrics fail.

Decisive artifact-level evidence, replicating verifier/test_outputs.py exactly:
  rise   : t(ego>=27) - t(ego>=3) over t <= 30 s      must be < 10 s
  over   : max(ego_speed) over t <= 30 s              must be < 31.5 m/s
  ss_err : |30 - mean(ego_speed, 25 <= t <= 30)|      must be < 0.5 m/s

Usage: python3 analysis_tools/acc_windup_analyze.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import statistics
import tarfile
from collections import defaultdict

import sys
STUDY = sys.argv[1] if len(sys.argv) > 1 else 'experiments/acc-windup-adv-20260924'
RUNS = os.path.join(STUDY, 'runs')

ANTIWINDUP = re.compile(
    r'if\s+not\s+saturated|conditional\s+integration|anti[-_ ]?windup|'
    r'clamp.*integral|integral\s*=\s*(?:max|min)\(',
    re.I)


def read_tgz_member(cell, suffix):
    for root, _d, files in os.walk(cell):
        for f in files:
            if f == 'agent-artifacts.tgz':
                try:
                    with tarfile.open(os.path.join(root, f)) as t:
                        for m in t.getmembers():
                            if m.name.endswith(suffix):
                                return t.extractfile(m).read().decode('utf-8', 'replace')
                except Exception:
                    return None
    return None


def metrics(text):
    if not text:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    try:
        pts = [(float(r['time']), float(r['ego_speed'])) for r in rows
               if r.get('time') not in (None, '') and r.get('ego_speed') not in (None, '')]
    except (KeyError, ValueError):
        return None
    cruise = [(t, v) for t, v in pts if t <= 30.0]
    if not cruise:
        return None
    t3 = next((t for t, v in cruise if v >= 3.0), None)
    t27 = next((t for t, v in cruise if v >= 27.0), None)
    rise = (t27 - t3) if (t3 is not None and t27 is not None) else None
    vmax = max(v for _, v in cruise)
    ss = [v for t, v in pts if 25.0 <= t <= 30.0]
    ss_err = abs(30.0 - (sum(ss) / len(ss))) if ss else None
    return dict(rows=len(rows), rise=rise, vmax=vmax, ss_err=ss_err,
                rise_ok=(rise is not None and rise < 10.0),
                overshoot_ok=(vmax < 31.5),
                ss_ok=(ss_err is not None and ss_err < 0.5))


def main():
    rows = []
    for cell in sorted(os.listdir(RUNS)):
        d = os.path.join(RUNS, cell)
        rp = os.path.join(d, 'result.json')
        if not os.path.isdir(d) or not os.path.exists(rp):
            continue
        r = json.load(open(rp))
        sim = read_tgz_member(d, 'simulation_results.csv')
        pid = read_tgz_member(d, 'pid_controller.py') or ''
        m = metrics(sim)
        rows.append(dict(
            cell=cell, condition=r.get('condition'), status=r.get('status'),
            score=r.get('score'), api_calls=r.get('api_calls'),
            total_tokens=r.get('total_tokens'),
            has_sim=sim is not None,
            rise=(m or {}).get('rise'), vmax=(m or {}).get('vmax'),
            ss_err=(m or {}).get('ss_err'),
            rise_ok=(m or {}).get('rise_ok'), overshoot_ok=(m or {}).get('overshoot_ok'),
            ss_ok=(m or {}).get('ss_ok'),
            speed_control_ok=bool(m and m['rise_ok'] and m['overshoot_ok'] and m['ss_ok']),
            pid_has_antiwindup=bool(ANTIWINDUP.search(pid)),
        ))
    json.dump(rows, open(os.path.join(STUDY, 'analysis.json'), 'w'),
              ensure_ascii=False, indent=1)

    hdr = (f"{'cell':48}{'score':>7}{'rise_s':>8}{'vmax':>8}{'ssErr':>7}"
           f"{'speedOK':>9}{'antiWU':>8}")
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        f = lambda x: ('  n/a' if x is None else f"{x:6.2f}")
        print(f"{r['cell'][:47]:48}{str(r['score']):>7}{f(r['rise'])}{f(r['vmax'])}"
              f"{f(r['ss_err'])}{str(r['speed_control_ok']):>9}"
              f"{str(r['pid_has_antiwindup']):>8}")
    print()
    g = defaultdict(list)
    for r in rows:
        g[r['condition']].append(r)
    print(f"{'condition':16}{'n':>3}{'mean score':>12}{'speedCtrl OK':>14}"
          f"{'anti-windup in pid_controller.py':>34}{'med vmax':>10}")
    for k in sorted(g):
        rs = g[k]
        sc = [x['score'] for x in rs if x['score'] is not None]
        vm = [x['vmax'] for x in rs if x['vmax'] is not None]
        print(f"{k:16}{len(rs):3}"
              f"{(statistics.mean(sc) if sc else float('nan')):12.3f}"
              f"{sum(1 for x in rs if x['speed_control_ok']):14}"
              f"{sum(1 for x in rs if x['pid_has_antiwindup']):34}"
              f"{(statistics.median(vm) if vm else -1):10.2f}")


if __name__ == '__main__':
    main()
