"""
RQ1-B  Types of inconsistencies.

Answers
  * Where does the contract break?  -> artifact-boundary distribution
    (Document-Code / Document-Document / Skill-Environment)   [Figure 3]
  * Which part of the contract breaks? -> contract-element ("facet") table
    (parameter / return / workflow / capability / resource / ...)
  * full three-level taxonomy -> appendix

Outputs
  outputs/table3_artifact_boundary.{csv,tex}
  outputs/table4_contract_facet.{csv,tex}
  outputs/table5_boundary_impact.{csv,tex}
  outputs/tableA1_l3_taxonomy.{csv,tex}
  outputs/fig3_boundary.csv, outputs/fig4_facets.csv

Run:  python3 analyze_types.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rq1_lib as L  # noqa: E402


def main() -> None:
    f = pd.read_csv(os.path.join(L.OUT, "rq1_findings.csv"))
    s = pd.read_csv(os.path.join(L.OUT, "rq1_skills.csv"))
    s["code_loc"] = pd.to_numeric(s.code_loc, errors="coerce").fillna(0)
    s["has_code"] = s.code_loc > 0
    f = f.merge(s[["corpus", "skill", "has_code"]], on=["corpus", "skill"])

    labels = [c.label for c in L.CORPORA]
    tot = {c.key: int((f.corpus == c.key).sum()) for c in L.CORPORA}

    # ------------------------------------------------------------------
    # Table 3 — artifact boundary (Figure 3 data)
    # ------------------------------------------------------------------
    rows = []
    for b in L.BOUNDARY_ORDER:
        row = [b]
        for c in L.CORPORA:
            n = int(((f.corpus == c.key) & (f.boundary == b)).sum())
            row += [n, f"{100 * n / tot[c.key]:.1f}%"]
        n_all = int((f.boundary == b).sum())
        row += [n_all, f"{100 * n_all / len(f):.1f}%"]
        rows.append(row)
    rows.append(["Total"] + sum([[tot[c.key], "100.0%"] for c in L.CORPORA], [])
                + [len(f), "100.0%"])
    two_line = []
    for l in labels:
        two_line += [r"\makecell{%s\\($n$)}" % l, r"\makecell{%s\\(\%%)}" % l]
    two_line += [r"\makecell{Both\\($n$)}", r"\makecell{Both\\(\%)}"]
    L.write_table(
        "table3_artifact_boundary",
        ["Artifact boundary"] + two_line,
        rows,
        caption=("Distribution of inconsistencies across artifact boundaries. "
                 "The boundary names the pair of artifacts whose contract is "
                 "violated: Document--Code (a described behaviour the "
                 "implementation does not honour), Document--Document (two "
                 "documentation artifacts disagree) and Skill--Environment "
                 "(a stated runtime assumption that does not hold)."),
        label="tab:rq1-boundary",
        align="l" + "r" * (len(rows[0]) - 1),
        raw_header=True,
    )
    # numeric copy for the plotting script (no '%' strings)
    pd.DataFrame([
        [b, int(((f.boundary == b) & (f.corpus == "wildskills")).sum()),
         100 * ((f.boundary == b) & (f.corpus == "wildskills")).sum() / tot["wildskills"],
         int(((f.boundary == b) & (f.corpus == "skillbench")).sum()),
         100 * ((f.boundary == b) & (f.corpus == "skillbench")).sum() / tot["skillbench"]]
        for b in L.BOUNDARY_ORDER],
        columns=["boundary", "github_n", "github_pct", "skillbench_n",
                 "skillbench_pct"]).to_csv(
        os.path.join(L.OUT, "fig3_boundary.csv"), index=False)

    # boundary split conditioned on whether the skill ships code
    cond_rows = []
    f["code_group"] = f.has_code.map({True: "ships code", False: "documentation only"})
    for grp in ("ships code", "documentation only"):
        for b in L.BOUNDARY_ORDER:
            n = int(((f.code_group == grp) & (f.boundary == b)).sum())
            d = int((f.code_group == grp).sum())
            cond_rows.append([grp, b, n, f"{100 * n / d:.1f}%"])
    L.write_table(
        "table3b_boundary_by_code",
        ["Skill content", "Artifact boundary", "Findings", "Share"],
        cond_rows,
        caption=("Artifact-boundary mix conditioned on whether the audited "
                 "skill ships executable code."),
        label="tab:rq1-boundary-code",
        align="llrr",
    )

    # ------------------------------------------------------------------
    # Table 4 — contract element (facet)
    # ------------------------------------------------------------------
    present = [x for x in L.FACET_ORDER if x in set(f.facet)]
    rows = []
    for facet in present:
        row = [L.FACET_DISPLAY[facet]]
        for c in L.CORPORA:
            n = int(((f.corpus == c.key) & (f.facet == facet)).sum())
            row += [n, f"{100 * n / tot[c.key]:.1f}%"]
        n_all = int((f.facet == facet).sum())
        row += [n_all, f"{100 * n_all / len(f):.1f}%"]
        rows.append(row)
    L.write_table(
        "table4_contract_facet",
        ["Contract element"] + two_line,
        rows,
        caption=("Which part of the skill contract is violated. The element is "
                 "derived from the taxonomy: level-3 for Document--Code "
                 "findings, level-2 for the other boundaries."),
        label="tab:rq1-facet",
        align="l" + "r" * (len(rows[0]) - 1),
        raw_header=True,
    )
    pd.DataFrame([
        [fac, int(((f.facet == fac) & (f.corpus == "wildskills")).sum()),
         100 * ((f.facet == fac) & (f.corpus == "wildskills")).sum() / tot["wildskills"],
         int(((f.facet == fac) & (f.corpus == "skillbench")).sum()),
         100 * ((f.facet == fac) & (f.corpus == "skillbench")).sum() / tot["skillbench"],
         int((f.facet == fac).sum()),
         100 * (f.facet == fac).sum() / len(f)]
        for fac in present],
        columns=["facet", "github_n", "github_pct", "skillbench_n",
                 "skillbench_pct", "both_n", "both_pct"]).to_csv(
        os.path.join(L.OUT, "fig4_facets.csv"), index=False)

    # ------------------------------------------------------------------
    # Table 5 — boundary x agent impact
    # ------------------------------------------------------------------
    rows = []
    for b in L.BOUNDARY_ORDER:
        sub = f[f.boundary == b]
        n = len(sub)
        rows.append([b, n, int(sub.blocks_execution.sum()),
                     f"{100 * sub.blocks_execution.mean():.1f}%",
                     int(sub.silent_error.sum()),
                     f"{100 * sub.silent_error.mean():.1f}%"])
    L.write_table(
        "table5_boundary_impact",
        ["Artifact boundary", "Findings", "Blocks execution", "Share",
         "Silent error", "Share"],
        rows,
        caption=("Agent impact by artifact boundary."),
        label="tab:rq1-boundary-impact",
        align="lrrrrr",
    )

    # ------------------------------------------------------------------
    # Table A1 — full three-level taxonomy (appendix)
    # ------------------------------------------------------------------
    rows = []
    g = f.groupby(["l1", "l2", "l3"], dropna=False)
    for (l1, l2, l3), sub in sorted(g, key=lambda kv: -len(kv[1])):
        l3s = "---" if (l3 is None or pd.isna(l3)) else str(l3)
        row = [L.BOUNDARY_SHORT.get(L.BOUNDARY.get(l1, l1), l1), l2, l3s]
        for c in L.CORPORA:
            n = int((sub.corpus == c.key).sum())
            row.append(n)
        row.append(len(sub))
        rows.append(row)
    L.write_table(
        "tableA1_l3_taxonomy",
        ["Boundary", "Level-2 type", "Level-3 type"] + labels + ["Total"],
        rows,
        caption=("Full three-level taxonomy with the number of confirmed "
                 "findings per type. Level-3 types are defined only for the "
                 "Document--Code boundary; Skill--Env. = Skill--Environment, "
                 "Doc--Code = Document--Code, Doc--Doc = Document--Document."),
        label="tab:rq1-taxonomy",
        align="lll" + "r" * (len(labels) + 1),
        size=r"\footnotesize",
        resize=True,
    )

    print("\nartifact boundary (both corpora):")
    print(f.boundary.value_counts().to_string())
    print("\ntop contract elements:")
    print(f.facet.value_counts().head(8).to_string())


if __name__ == "__main__":
    main()
