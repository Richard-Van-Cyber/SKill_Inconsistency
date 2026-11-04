"""
Aggregate the persisted verification verdicts and quantify the impact on RQ1.

Reads  outputs/verdicts/pass1_*.json  and  outputs/verdicts/pass2_*.json
       outputs/verify_input.json      (finding metadata)
Writes outputs/verification_results.csv
       outputs/verification_summary.md
       outputs/verification_stats.json

Run:  python3 aggregate_verification.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")

# taxonomy -> artifact boundary (same mapping as the RQ1 analysis)
BOUNDARY = {"environmental": "Skill-Environment",
            "implementation": "Document-Code",
            "document": "Document-Document"}


def load_verdicts() -> dict:
    v = {}
    for f in sorted(glob.glob(os.path.join(OUT, "verdicts", "pass1_*.json"))):
        for r in json.load(open(f))["results"]:
            v[r["key"]] = dict(r, phase="pass1")
    for f in sorted(glob.glob(os.path.join(OUT, "verdicts", "pass2_*.json"))):
        for r in json.load(open(f))["results"]:
            v[r["key"]] = dict(r, phase="pass2")
    return v


def main() -> None:
    items = json.load(open(os.path.join(OUT, "verify_input.json")))
    verdicts = load_verdicts()
    assert len(verdicts) == len(items), (len(verdicts), len(items))

    rows = []
    for it in items:
        v = verdicts[it["key"]]
        claim = it["claim"]
        if v["verdict"] == "mislabeled":
            l1, l2, l3 = v["corrected_l1"], v["corrected_l2"], v["corrected_l3"]
        else:
            l1, l2, l3 = claim["l1"], claim["l2"], claim["l3"]
        ev = it["evidence"]
        rows.append(dict(
            key=it["key"], skill=it["skill"], finding=it["finding"],
            checker=it["checker"], severity=it["severity"],
            confidence=it["confidence"],
            claimed_l1=claim["l1"], claimed_l2=claim["l2"], claimed_l3=claim["l3"],
            verdict=v["verdict"], reason_code=v["reason_code"],
            corrected_l1=v["corrected_l1"], corrected_l2=v["corrected_l2"],
            corrected_l3=v["corrected_l3"],
            final_l1=l1, final_l2=l2, final_l3=l3,
            v_confidence=v["confidence"], phase=v["phase"],
            reason=(v["reason"] or "").replace("\n", " "),
            ev_match=";".join(sorted({e["match"] for e in ev})),
            ev_not_found=any(e["match"] in ("not_found", "synthetic") for e in ev),
        ))

    with open(os.path.join(OUT, "verification_results.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    vd = Counter(r["verdict"] for r in rows)
    survived = [r for r in rows if r["verdict"] in ("confirmed", "mislabeled")]
    strict = [r for r in rows if r["verdict"] == "confirmed"]

    stats = {
        "n_findings": n,
        "verdicts": dict(vd),
        "survived_relaxed": len(survived),
        "survived_strict": len(strict),
        "by_l1": {}, "by_l2": {}, "by_checker": {}, "by_severity": {},
        "by_confidence": {}, "reason_codes": dict(Counter(
            r["reason_code"] for r in rows if r["verdict"] == "invalid")),
        "corrected_flows": dict(Counter(
            f"{r['claimed_l1']} -> {r['corrected_l1']}"
            for r in rows if r["verdict"] == "mislabeled")),
    }
    for field, key in (("claimed_l1", "by_l1"), ("claimed_l2", "by_l2"),
                       ("checker", "by_checker"), ("severity", "by_severity"),
                       ("confidence", "by_confidence")):
        agg = defaultdict(Counter)
        for r in rows:
            agg[r[field] or "(none)"][r["verdict"]] += 1
        stats[key] = {k: dict(v) for k, v in sorted(agg.items(),
                                                    key=lambda kv: -sum(kv[1].values()))}

    # ---------------- impact on the RQ1 numbers ----------------
    per_skill = defaultdict(lambda: {"all": 0, "strict": 0, "relaxed": 0})
    for r in rows:
        per_skill[r["skill"]]["all"] += 1
        if r["verdict"] == "confirmed":
            per_skill[r["skill"]]["strict"] += 1
        if r["verdict"] in ("confirmed", "mislabeled"):
            per_skill[r["skill"]]["relaxed"] += 1
    import glob as _glob
    audited = {os.path.basename(os.path.dirname(f)) for f in _glob.glob(os.path.join(
        os.path.dirname(HERE), "skillbench_audit", "*", "audit_report.json"))}
    n_skills = len(audited)
    prev = {
        "skills": n_skills,
        "tasks_with_findings": len({r["skill"] for r in rows}),
        "with_finding_all": sum(1 for s in per_skill.values() if s["all"]),
        "with_finding_strict": sum(1 for s in per_skill.values() if s["strict"]),
        "with_finding_relaxed": sum(1 for s in per_skill.values() if s["relaxed"]),
    }
    counts = {k: [s[k] for s in per_skill.values()] for k in ("all", "strict", "relaxed")}

    def mean(x):
        return sum(x) / len(x) if x else 0

    def pct_at_least(x, v):
        return 100 * sum(1 for i in x if i >= v) / len(x) if x else 0

    impact = {
        "skills": n_skills,
        "prevalence": {k: round(100 * prev[f"with_finding_{k}"] / n_skills, 1)
                       for k in ("all", "strict", "relaxed")},
        "total_findings": {k: sum(counts[k]) for k in counts},
        "mean": {k: round(mean(counts[k]), 2) for k in counts},
        "median": {k: sorted(counts[k])[len(counts[k]) // 2] for k in counts},
        "max": {k: max(counts[k]) for k in counts},
    }
    for k in counts:
        impact[f"p90_{k}"] = round(sorted(counts[k])[int(0.9 * len(counts[k]))], 1)

    boundary = {}
    sel = {"all": rows,
           "strict": [r for r in rows if r["verdict"] == "confirmed"],
           "relaxed": [r for r in rows if r["verdict"] in ("confirmed", "mislabeled")]}
    for k, sub in sel.items():
        field = "claimed_l1" if k == "all" else "final_l1"
        boundary[k] = dict(Counter(BOUNDARY.get(r[field], "Other") for r in sub))
    impact["boundary"] = boundary

    stats["impact_on_rq1"] = impact
    json.dump(stats, open(os.path.join(OUT, "verification_stats.json"), "w"),
              ensure_ascii=False, indent=1)

    # ---------------- markdown summary ----------------
    L = []
    A = L.append
    A("# SkillBench finding verification — results\n")
    A(f"Findings verified: **{n}** across **{len({r['skill'] for r in rows})}** tasks "
      f"that received findings ({n_skills} audited SkillBench tasks in total).\n")
    A("| verdict | findings | share |")
    A("|---|---:|---:|")
    for k in ("confirmed", "mislabeled", "invalid", "unverifiable"):
        if vd.get(k):
            A(f"| {k} | {vd[k]} | {100 * vd[k] / n:.1f}% |")
    A(f"| **survive (confirmed + mislabeled)** | **{len(survived)}** | "
      f"**{100 * len(survived) / n:.1f}%** |")
    A(f"| **confirmed only** | **{len(strict)}** | **{100 * len(strict) / n:.1f}%** |")

    A("\n## Why findings were rejected\n")
    A("| reason code | findings |")
    A("|---|---:|")
    for k, v in Counter(r["reason_code"] for r in rows
                        if r["verdict"] == "invalid").most_common():
        A(f"| {k or '(unspecified)'} | {v} |")

    A("\n## Survival by claimed layer\n")
    A("| claimed L1 | total | confirmed | mislabeled | invalid | survive % |")
    A("|---|---:|---:|---:|---:|---:|")
    for l1, c in stats["by_l1"].items():
        t = sum(c.values())
        s = c.get("confirmed", 0) + c.get("mislabeled", 0)
        A(f"| {l1} | {t} | {c.get('confirmed', 0)} | {c.get('mislabeled', 0)} | "
          f"{c.get('invalid', 0)} | {100 * s / t:.1f}% |")

    A("\n## Survival by producing checker\n")
    A("| checker | total | confirmed | mislabeled | invalid | survive % |")
    A("|---|---:|---:|---:|---:|---:|")
    for ck, c in stats["by_checker"].items():
        t = sum(c.values())
        s = c.get("confirmed", 0) + c.get("mislabeled", 0)
        A(f"| {ck} | {t} | {c.get('confirmed', 0)} | {c.get('mislabeled', 0)} | "
          f"{c.get('invalid', 0)} | {100 * s / t:.1f}% |")

    A("\n## Survival by claimed level-2 type (top 12)\n")
    A("| L2 | total | confirmed | mislabeled | invalid | survive % |")
    A("|---|---:|---:|---:|---:|---:|")
    for l2, c in list(stats["by_l2"].items())[:12]:
        t = sum(c.values())
        s = c.get("confirmed", 0) + c.get("mislabeled", 0)
        A(f"| {l2} | {t} | {c.get('confirmed', 0)} | {c.get('mislabeled', 0)} | "
          f"{c.get('invalid', 0)} | {100 * s / t:.1f}% |")

    A("\n## Mislabeling flows (claimed layer -> corrected layer)\n")
    A("| flow | findings |")
    A("|---|---:|")
    for k, v in Counter(f"{r['claimed_l1']} -> {r['corrected_l1']}"
                        for r in rows if r["verdict"] == "mislabeled").most_common():
        A(f"| {k} | {v} |")

    A("\n## Effect on the RQ1 numbers\n")
    A("| metric | as audited | confirmed only | confirmed + relabelled |")
    A("|---|---:|---:|---:|")
    A(f"| tasks with >=1 inconsistency | {prev['with_finding_all']} | "
      f"{prev['with_finding_strict']} | {prev['with_finding_relaxed']} |")
    A(f"| prevalence | {impact['prevalence']['all']}% | "
      f"{impact['prevalence']['strict']}% | {impact['prevalence']['relaxed']}% |")
    A(f"| total findings | {impact['total_findings']['all']} | "
      f"{impact['total_findings']['strict']} | {impact['total_findings']['relaxed']} |")
    A(f"| mean per task | {impact['mean']['all']} | {impact['mean']['strict']} | "
      f"{impact['mean']['relaxed']} |")
    A(f"| median per task | {impact['median']['all']} | {impact['median']['strict']} | "
      f"{impact['median']['relaxed']} |")
    A(f"| P90 per task | {impact['p90_all']} | {impact['p90_strict']} | "
      f"{impact['p90_relaxed']} |")

    A("\nArtifact-boundary mix (share of findings):\n")
    A("| layer | as audited | confirmed only | confirmed + relabelled |")
    A("|---|---:|---:|---:|")
    for b in ("Document-Code", "Skill-Environment", "Document-Document"):
        def sh(k):
            d = boundary[k]
            t = sum(d.values())
            return f"{100 * d.get(b, 0) / t:.1f}%" if t else "n/a"
        A(f"| {b} | {sh('all')} | {sh('strict')} | {sh('relaxed')} |")

    open(os.path.join(OUT, "verification_summary.md"), "w",
         encoding="utf-8").write("\n".join(L) + "\n")

    print(f"verdicts: {dict(vd)}")
    print(f"survive: {len(survived)}/{n} ({100 * len(survived) / n:.1f}%)  "
          f"confirmed only: {len(strict)} ({100 * len(strict) / n:.1f}%)")
    print("reason codes:", stats["reason_codes"])
    print("prevalence all/strict/relaxed:",
          impact["prevalence"]["all"], impact["prevalence"]["strict"],
          impact["prevalence"]["relaxed"])
    print("wrote outputs/verification_results.csv, verification_summary.md, "
          "verification_stats.json")


def R_BOUNDARY(r):
    return BOUNDARY.get(r["final_l1"], "Other")


if __name__ == "__main__":
    main()
