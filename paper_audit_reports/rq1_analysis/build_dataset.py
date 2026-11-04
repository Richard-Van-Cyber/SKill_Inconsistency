"""
RQ1 step 1 — build the tidy dataset.

Reads every audit report in the two corpora and writes

    outputs/rq1_findings.csv   one row per validated finding
    outputs/rq1_skills.csv     one row per audited skill (+ contract surface)

Run:  python3 build_dataset.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rq1_lib as L  # noqa: E402


def load_domains() -> dict[tuple[str, str], dict]:
    """Category labels from paper_audit_reports/skill_category_distribution.csv"""
    out: dict[tuple[str, str], dict] = {}
    if not os.path.exists(L.DOMAIN_CSV):
        return out
    with open(L.DOMAIN_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ds = "wildskills" if row["dataset"] == "wildskills" else "skillbench"
            out[(ds, row["skill_dir"])] = {
                "domain": row["category"],
                "subcategory": row.get("subcategory") or "",
            }
    return out


def main() -> None:
    domains = load_domains()
    findings: list[dict] = []
    skills: list[dict] = []

    for corpus in L.CORPORA:
        reports = sorted(glob.glob(os.path.join(corpus.audit_dir, "*",
                                                "audit_report.json")))
        print(f"[{corpus.label}] {len(reports)} reports")
        for rep in reports:
            name = os.path.basename(os.path.dirname(rep))
            d = json.load(open(rep, encoding="utf-8"))
            meta = d.get("meta", {})
            sdir = L.resolve_skill_dir(name, meta.get("skill_dir"))

            metrics = L.measure_skill(sdir) if sdir else {
                "contract_claims": 0, "doc_claims": 0, "code_claims": 0,
                "code_loc": 0, "doc_lines": 0, "n_files": 0,
                "n_doc_files": 0, "n_code_files": 0,
            }
            dom = domains.get((corpus.key, name), {})
            flist = d.get("findings", []) or []

            for fd in flist:
                l1 = (fd.get("taxonomy_l1") or "").strip()
                l2 = L.normalise_l2(l1, fd.get("taxonomy_l2"))
                l3 = (fd.get("taxonomy_l3") or "").strip() or None
                ai = fd.get("agent_impact") or {}
                findings.append({
                    "corpus": corpus.key,
                    "skill": name,
                    "finding_id": fd.get("id"),
                    "l1": l1,
                    "l2": l2,
                    "l3": l3 or "",
                    "boundary": L.boundary_of(l1),
                    "facet": L.facet_of(l1, l2, l3),
                    "severity": (fd.get("severity") or "").strip(),
                    "confidence": (fd.get("confidence") or "").strip(),
                    "validation_status": (fd.get("validation_status") or "").strip(),
                    "source_checker": (fd.get("source_checker") or "").strip(),
                    "blocks_execution": bool(ai.get("blocks_execution")),
                    "silent_error": bool(ai.get("produces_silent_error")),
                    "impact_class": (ai.get("impact_class") or "").strip(),
                })

            sev = {}
            for fd in flist:
                s = (fd.get("severity") or "").strip().lower()
                sev[s] = sev.get(s, 0) + 1
            skills.append({
                "corpus": corpus.key,
                "skill": name,
                "domain": dom.get("domain", ""),
                "subcategory": dom.get("subcategory", ""),
                "n_findings": len(flist),
                "n_raw_findings": (d.get("summary") or {}).get("raw_finding_count", ""),
                "n_suppressed": (d.get("summary") or {}).get("suppressed_count", ""),
                "n_critical": sev.get("critical", 0),
                "n_high": sev.get("high", 0),
                "n_medium": sev.get("medium", 0),
                "n_low": sev.get("low", 0),
                "n_blocking": sum(1 for fd in flist
                                  if (fd.get("agent_impact") or {}).get("blocks_execution")),
                "n_silent": sum(1 for fd in flist
                                if (fd.get("agent_impact") or {}).get("produces_silent_error")),
                "total_files": (d.get("skill_map_summary") or {}).get("total_files", ""),
                "functions_parsed": (d.get("preflight") or {}).get("functions_parsed", ""),
                "skill_dir": sdir or "",
                **metrics,
            })

    with open(os.path.join(L.OUT, "rq1_findings.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(findings[0].keys()))
        w.writeheader()
        w.writerows(findings)
    with open(os.path.join(L.OUT, "rq1_skills.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(skills[0].keys()))
        w.writeheader()
        w.writerows(skills)

    print(f"  findings: {len(findings)}  -> outputs/rq1_findings.csv")
    print(f"  skills:   {len(skills)}  -> outputs/rq1_skills.csv")
    for c in L.CORPORA:
        sub = [s for s in skills if s["corpus"] == c.key]
        print(f"    {c.label:<14} skills={len(sub):4d} "
              f"findings={sum(s['n_findings'] for s in sub):5d} "
              f"claims={sum(s['contract_claims'] for s in sub):7d} "
              f"LOC={sum(s['code_loc'] for s in sub):7d}")


if __name__ == "__main__":
    main()
