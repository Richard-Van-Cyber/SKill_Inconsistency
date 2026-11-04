#!/usr/bin/env python3
"""Rank the 87 audited skill packages by the impact of their inconsistencies on
task completion (success rate, token cost, wall-clock cost).

Inputs
------
tasks/<task>/audit_report.json           static inconsistency audit (this repo's detector)
/tmp/exposure_baseline.json              per-finding runtime exposure over the paper-v1 runs
                                         (produced by analysis_tools/exposure_scan_baseline.py)
/tmp/baseline_runs.json                  per-run reward / token / timing for the same runs
                                         (produced by analysis_tools/parse_baseline_runs.py)

Outputs
-------
skill_inconsistency_impact_ranking.csv   all 87 tasks, every column
skill_inconsistency_impact_top30.md      the report

Run from the workspace root:
    python3 analysis_tools/exposure_scan_baseline.py
    python3 analysis_tools/parse_baseline_runs.py
    python3 analysis_tools/impact_ranking.py
"""
from __future__ import annotations

import csv
import glob
import json
import math
import statistics
from collections import Counter, defaultdict

SEV_W = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.25}
CONF_W = {"verified": 1.0, "inferred": 0.7, "speculative": 0.3}
IMPACT_W = {"silent": 0.9, "may_block_if": 0.5, "cosmetic": 0.05}
# impact_class == "verified" is a detector schema bug (a confidence value written
# into the impact field); treat it as an unknown mid-strength impact.
IMPACT_W["verified"] = 0.5

WEIGHTS = dict(success=0.40, token=0.20, time=0.15, latent=0.25)


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_reports():
    out = {}
    for p in sorted(glob.glob("tasks/*/audit_report.json")):
        task = p.split("/")[1]
        out[task] = json.load(open(p))
    return out


def finding_weight(f):
    sev = SEV_W.get((f.get("severity") or "").lower(), 1.0)
    conf = CONF_W.get((f.get("confidence") or "").lower(), 0.5)
    imp = IMPACT_W.get((f.get("agent_impact") or {}).get("impact_class"), 0.5)
    if (f.get("agent_impact") or {}).get("blocks_execution"):
        imp = max(imp, 1.0)
    return sev * conf * imp


def minmax_norm(values):
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def norm_log(values):
    return minmax_norm([math.log1p(max(v, 0.0)) for v in values])


# --------------------------------------------------------------------------- #
# build the table
# --------------------------------------------------------------------------- #
def build():
    reports = load_reports()
    exposure = json.load(open("/tmp/exposure_baseline.json"))
    runs = json.load(open("/tmp/baseline_runs.json"))

    runs_by_task = defaultdict(list)
    for r in runs:
        runs_by_task[r["task"]].append(r)

    rows = []
    for task, rep in sorted(reports.items()):
        summary = rep.get("summary") or {}
        smap = rep.get("skill_map_summary") or {}
        findings = rep.get("findings") or []
        exp = exposure.get(task, {})
        exp_by_id = {x["id"]: x for x in (exp.get("findings") or [])}
        n_runs = exp.get("n_runs") or 0

        # ---- comprehension validity ------------------------------------- #
        n_files = smap.get("total_files") or 0
        n_components = len(smap.get("components") or [])
        comprehension_ok = bool(n_components)
        invalid_reason = ""
        if n_files and not n_components:
            invalid_reason = "comprehension produced 0 components"

        # ---- static risk -------------------------------------------------- #
        latent = 0.0          # every finding
        reachable = 0.0       # exposure-weighted
        n_exposed = 0
        n_file_level = 0
        verified_blockers = 0
        verified_silent = 0
        best = None  # (weight, id, severity, impact_class, file, rationale)
        for f in findings:
            w = finding_weight(f)
            latent += w
            x = exp_by_id.get(f.get("id"))
            p_hit = 0.0
            if x and n_runs:
                p_hit = (x["n_file"] + x["n_doc"]) / n_runs
                if x["n_file"]:
                    n_file_level += 1
            if p_hit > 0:
                n_exposed += 1
                score = w * p_hit
                if best is None or score > best[0]:
                    ev = (f.get("evidence") or {}).get("source_a") or {}
                    best = (score, f.get("id"), f.get("severity"),
                            (f.get("agent_impact") or {}).get("impact_class"),
                            ev.get("file"), (f.get("rationale") or "")[:400],
                            (f.get("agent_impact") or {}).get("impact_description") or "")
            reachable += w * p_hit
            if f.get("confidence") == "verified":
                if (f.get("agent_impact") or {}).get("blocks_execution"):
                    verified_blockers += 1
                if (f.get("agent_impact") or {}).get("produces_silent_error"):
                    verified_silent += 1

        # ---- empirical outcome -------------------------------------------- #
        rs = runs_by_task.get(task, [])
        graded = [r for r in rs if r.get("reward") is not None]
        success = (sum(r["reward"] for r in graded) / len(graded)) if graded else None
        failed = [r for r in graded if r["reward"] < 0.5]

        # baseline_runs.json uses flat keys: t_total / t_agent / t_env / t_verifier
        def med(key, sel):
            vals = []
            for r in sel:
                if key == "tokens":
                    u = r.get("usage")
                    if u:
                        vals.append(u["total_tokens"])
                else:
                    v = r.get(key)
                    if v is not None:
                        vals.append(v)
            return statistics.median(vals) if vals else None

        med_tokens = med("tokens", graded)
        med_total = med("t_total", graded)
        med_agent = med("t_agent", graded)
        fail_tokens = med("tokens", failed)
        fail_total = med("t_total", failed)
        fail_agent = med("t_agent", failed)

        tot_tokens = sum(r["usage"]["total_tokens"] for r in graded if r.get("usage"))
        fail_tokens_sum = sum(r["usage"]["total_tokens"] for r in failed if r.get("usage"))
        tot_time = sum(r.get("t_total") or 0 for r in graded)
        fail_time_sum = sum(r.get("t_total") or 0 for r in failed)

        rows.append(dict(
            task=task,
            n_runs_baseline=len(graded),
            comprehension_ok=comprehension_ok,
            invalid_reason=invalid_reason,
            n_files=n_files,
            n_components=n_components,
            n_sub_skills=len(smap.get("sub_skills") or []),
            sub_skills="|".join(smap.get("sub_skills") or []),
            n_findings=len(findings),
            n_critical=summary.get("critical_count") or 0,
            n_high=summary.get("high_count") or 0,
            n_medium=summary.get("medium_count") or 0,
            n_low=summary.get("low_count") or 0,
            suppressed_by_rule=summary.get("suppressed_by_rule") or 0,
            raw_finding_count=summary.get("raw_finding_count") or 0,
            verified_blockers=verified_blockers,
            verified_silent=verified_silent,
            latent_risk=round(latent, 3),
            reachable_risk=round(reachable, 3),
            n_findings_exposed=n_exposed,
            n_findings_file_level=n_file_level,
            skill_load_rate=round((exp.get("skill_load_runs") or 0) / n_runs, 3) if n_runs else None,
            success_rate=round(success, 4) if success is not None else None,
            med_tokens=med_tokens,
            med_total_s=med_total,
            med_agent_s=med_agent,
            fail_med_tokens=fail_tokens,
            fail_med_total_s=fail_total,
            fail_med_agent_s=fail_agent,
            fail_token_share=round(fail_tokens_sum / tot_tokens, 3) if tot_tokens else None,
            fail_time_share=round(fail_time_sum / tot_time, 3) if tot_time else None,
            top_exposed_id=best[1] if best else None,
            top_exposed_severity=best[2] if best else None,
            top_exposed_impact=best[3] if best else None,
            top_exposed_file=best[4] if best else None,
            top_exposed_rationale=(best[5] if best else ""),
            top_exposed_impact_desc=(best[6] if best else ""),
        ))

    # ---- dimension scores ----------------------------------------------- #
    # Damage (what the task loses when it does not complete) is measured only on
    # tasks that have baseline runs. Reachability gates it: an inconsistency that
    # never entered the agent's context cannot have caused anything.
    measured = [r for r in rows if r["success_rate"] is not None]
    s_n = minmax_norm([1.0 - r["success_rate"] for r in measured])
    t_n = norm_log([r["fail_med_tokens"] or 0 for r in measured])
    w_n = norm_log([r["fail_med_total_s"] or 0 for r in measured])
    # reachability gate is normalised over tasks that actually have findings
    withf = [r for r in measured if r["n_findings"] > 0]
    g_n = norm_log([r["reachable_risk"] for r in withf])
    gate = {r["task"]: g for r, g in zip(withf, g_n)}

    for r, s, t, w in zip(measured, s_n, t_n, w_n):
        r["dim_success"] = round(100 * s, 1)
        r["dim_token"] = round(100 * t, 1)
        r["dim_time"] = round(100 * w, 1)
        g = gate.get(r["task"], 0.0)
        r["dim_gate"] = round(100 * g, 1)
        if r["n_findings"] == 0:
            # the audit found no inconsistency at all -> no inconsistency impact
            r["IIS"] = 0.0
            r["IIS_note"] = "no findings"
            continue
        damage = 0.50 * s + 0.30 * t + 0.20 * w
        r["dim_damage"] = round(100 * damage, 1)
        r["IIS"] = round(100 * g * (0.30 + 0.70 * damage), 1)
        r["IIS_note"] = ""
        r["IIS_gate_off"] = round(100 * (0.30 + 0.70 * damage), 1)

    for r in rows:
        if r["success_rate"] is None:
            for k in ("dim_success", "dim_token", "dim_time", "dim_gate",
                      "dim_damage", "IIS", "IIS_gate_off"):
                r[k] = None
            r["IIS_note"] = "no baseline runs"

    # tiers: how much we trust the exposure measurement
    for r in rows:
        if r["success_rate"] is None:
            r["tier"] = "D 不可测"
        elif not r["comprehension_ok"]:
            r["tier"] = "E 报告无效"
        elif r["reachable_risk"] > 0 and (r["n_runs_baseline"] or 0) >= 2:
            r["tier"] = "A 可直接排序"
        elif r["reachable_risk"] > 0:
            r["tier"] = "B 单次运行"
        else:
            r["tier"] = "C 不一致性不可达"

    return rows


# --------------------------------------------------------------------------- #
# validity checks reported in the markdown
# --------------------------------------------------------------------------- #
def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def correlations(rows):
    sub = [r for r in rows if r["n_findings"] > 0 and r["success_rate"] is not None]
    out = {}
    for label, key in [("reachable_risk", "reachable_risk"),
                       ("latent_risk", "latent_risk"),
                       ("n_findings", "n_findings"),
                       ("skill_load_rate", "skill_load_rate")]:
        for target in ("success_rate", "fail_med_tokens", "fail_med_total_s"):
            xs = [r[key] for r in sub if r.get(key) is not None and r.get(target) is not None]
            ys = [r[target] for r in sub if r.get(key) is not None and r.get(target) is not None]
            out[(label, target)] = (pearson(xs, ys), len(xs))
    return out, len(sub)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    rows = build()

    with open("skill_inconsistency_impact_ranking.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # measured tasks that actually carry a reachable inconsistency
    ranked = [r for r in rows if r["IIS"] is not None and (r["reachable_risk"] or 0) > 0]
    ranked.sort(key=lambda r: -r["IIS"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i

    corr, n_corr = correlations(rows)
    valid = [r for r in rows if r["comprehension_ok"]]
    invalid = [r for r in rows if not r["comprehension_ok"]]
    top30 = ranked[:30]

    print(f"reports={len(rows)} valid={len(valid)} invalid={len(invalid)} "
          f"with_findings={sum(1 for r in rows if r['n_findings'])} "
          f"reachable+measured={len(ranked)}")
    print(f"corr set n={n_corr}")
    for k, v in corr.items():
        print(f"  corr({k[0]}, {k[1]}) = {v[0]:+.3f} (n={v[1]})")
    print()
    hdr = (f"{'#':>3} {'task':44}{'IIS':>6}{'S':>6}{'T':>6}{'W':>6}{'gate':>6}"
           f"{'succ':>6}{'find':>5}{'exp':>4}{'file':>5}{'tier':>16}")
    print(hdr)
    for r in top30:
        print(f"{r['rank']:3} {r['task']:44}{r['IIS']:6.1f}{r['dim_success']:6.1f}{r['dim_token']:6.1f}"
              f"{r['dim_time']:6.1f}{r['dim_gate']:6.1f}{r['success_rate']*100:5.0f}%"
              f"{r['n_findings']:5}{r['n_findings_exposed']:4}{r['n_findings_file_level']:5}{r['tier']:>16}")

    json.dump(dict(rows=rows, corr={f"{k[0]}|{k[1]}": v for k, v in corr.items()},
                   n_corr=n_corr, top30=[r["task"] for r in top30]),
              open("/tmp/impact_ranking.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
