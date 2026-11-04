"""
Recompute the RQ1 statistics with the verified SkillBench findings.

SkillBench findings that the verification rejected (verdict == invalid) are
dropped, and findings that were relabelled (verdict == mislabeled) use their
corrected level-1/2/3 labels.  GitHub findings are kept as audited - they have
NOT been verified yet - and are flagged as such in every output.

Inputs : ../rq1_analysis/outputs/rq1_findings.csv, rq1_skills.csv
         outputs/verification_results.csv
Outputs: outputs/verified/rq1_findings_verified.csv
         outputs/verified/{tableA..tableE}.{csv,tex}
         outputs/verified/summary.json
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
VOUT = os.path.join(OUT, "verified")
os.makedirs(VOUT, exist_ok=True)
RQ1 = os.path.join(os.path.dirname(HERE), "rq1_analysis")

BOUNDARY = {"environmental": "Skill\u2013Environment",
            "implementation": "Document\u2013Code",
            "document": "Document\u2013Document"}
BOUNDARY_ORDER = ["Document\u2013Code", "Document\u2013Document",
                  "Skill\u2013Environment"]
CHECKER_LABEL = {
    "impl_semantic_conflict_checker": "impl-symbolic",
}


def tex_escape(s):
    out = []
    for ch in str(s):
        out.append({"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#",
                    "$": r"\$"}.get(ch, ch))
    return "".join(out)


def write_table(stem, header, rows, caption, label, note="", align=None,
                size=r"\small", raw_header=False):
    with open(os.path.join(VOUT, f"{stem}.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    align = align or ("l" + "r" * (len(header) - 1))
    L = [r"\begin{table}[t]", r"  \centering", r"  \caption{%s}" % caption,
         r"  \label{%s}" % label, "  %s" % size, r"  \setlength{\tabcolsep}{4pt}",
         r"  \resizebox{\ifdim\width>\linewidth \linewidth\else\width\fi}{!}{%",
         r"  \begin{tabular}{%s}" % align, r"    \toprule",
         "    " + " & ".join(str(h) if raw_header else tex_escape(h)
                             for h in header) + r" \\", r"    \midrule"]
    for row in rows:
        L.append("    " + " & ".join(tex_escape(c) for c in row) + r" \\")
    L += [r"    \bottomrule", r"  \end{tabular}", r"  }%"]
    if note:
        L += [r"  \\[2pt]", r"  \begin{minipage}{\linewidth}",
              r"    \footnotesize\raggedright " + note, r"  \end{minipage}"]
    L += [r"\end{table}", ""]
    open(os.path.join(VOUT, f"{stem}.tex"), "w", encoding="utf-8").write(
        "\n".join(L))
    print(f"  table -> outputs/verified/{stem}.csv/.tex")


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    f = pd.read_csv(os.path.join(RQ1, "outputs", "rq1_findings.csv"))
    s = pd.read_csv(os.path.join(RQ1, "outputs", "rq1_skills.csv"))
    v = pd.read_csv(os.path.join(OUT, "verification_results.csv"))
    return f, s, v


def build_verified(f: pd.DataFrame, v: pd.DataFrame) -> pd.DataFrame:
    v = v.rename(columns={"finding": "finding_id"})
    f = f.merge(v[["skill", "finding_id", "verdict", "reason_code",
                   "final_l1", "final_l2", "final_l3", "claimed_l1",
                   "claimed_l2", "claimed_l3"]],
                on=["skill", "finding_id"], how="left")
    f["verified"] = f["corpus"].ne("skillbench")          # GitHub: not verified
    f["kept"] = True
    sb = f.corpus == "skillbench"
    f.loc[sb, "verified"] = True
    f.loc[sb, "kept"] = f.loc[sb, "verdict"].isin(["confirmed", "mislabeled"])
    # apply corrected labels for relabelled SkillBench findings
    fix = sb & f["verdict"].eq("mislabeled") & f["kept"]
    f.loc[fix, "l1"] = f.loc[fix, "final_l1"]
    f.loc[fix, "l2"] = f.loc[fix, "final_l2"]
    f.loc[fix, "l3"] = f.loc[fix, "final_l3"].replace({"none": ""})
    f["boundary"] = f["l1"].map(BOUNDARY).fillna("Other")
    # pure "as audited" view: always the *claimed* labels
    claim_l1 = f["claimed_l1"].where(sb, f["l1"])
    f["boundary_claimed"] = claim_l1.map(BOUNDARY).fillna("Other")
    f["l2_claimed"] = f["claimed_l2"].where(sb, f["l2"])
    return f


def main() -> None:
    f, s, v = load()
    fv = build_verified(f, v)
    fv.to_csv(os.path.join(VOUT, "rq1_findings_verified.csv"), index=False)

    for c in ("n_findings", "contract_claims", "code_loc"):
        s[c] = pd.to_numeric(s[c], errors="coerce").fillna(0)
    sb_skills = s[s.corpus == "skillbench"].copy()
    gh_skills = s[s.corpus == "wildskills"].copy()

    kept_sb = fv[(fv.corpus == "skillbench") & fv.kept]
    n_sb = len(sb_skills)

    summary = {}

    # ---------------- A. prevalence & density ----------------
    def col(g, findings):
        n = len(g)
        with_f = findings.skill.nunique()
        cnt = findings.groupby("skill").size()
        prof = g.set_index("skill").index
        vec = [int(cnt.get(x, 0)) for x in prof]
        vec_sorted = sorted(vec)
        import numpy as np
        v_arr = np.array(vec, dtype=float)
        cl = g.set_index("skill")["contract_claims"]
        dens = [int(cnt.get(x, 0)) / cl[x] * 100 for x in prof if cl[x] > 0]
        return {
            "n_skills": n,
            "with_findings": with_f,
            "prevalence": 100 * with_f / n,
            "total": int(len(findings)),
            "mean": v_arr.mean(),
            "median": float(np.median(v_arr)),
            "p90": float(np.percentile(v_arr, 90)),
            "max": int(v_arr.max()),
            "dens_median": float(np.median(dens)),
        }

    A = {"GitHub (as audited, unverified)": col(gh_skills,
                                                fv[fv.corpus == "wildskills"]),
         "SkillBench (as audited)": col(sb_skills,
                                        fv[fv.corpus == "skillbench"]),
         "SkillBench (verified)": col(sb_skills, kept_sb)}
    summary["prevalence"] = A

    metrics = [
        ("Skills audited", "n_skills", "{:.0f}"),
        ("Skills with at least one inconsistency", "with_findings", "{:.0f}"),
        ("Prevalence (%)", "prevalence", "{:.1f}"),
        ("Total inconsistencies", "total", "{:.0f}"),
        ("Mean per skill", "mean", "{:.2f}"),
        ("Median per skill", "median", "{:.0f}"),
        ("P90 per skill", "p90", "{:.0f}"),
        ("Max per skill", "max", "{:.0f}"),
        ("Inconsistencies per 100 contract claims (median skill)",
         "dens_median", "{:.2f}"),
    ]
    rows = [[lbl] + [fmt.format(A[c][k]) for c in A] for lbl, k, fmt in metrics]
    write_table("table1_prevalence_verified",
                ["Metric"] + list(A),
                rows,
                caption=("Prevalence and density before and after verifying the "
                         "SkillBench findings. Only SkillBench has been verified; "
                         "the GitHub column is the raw audit output."),
                label="tab:rq1-verified-prevalence",
                note=("GitHub findings have not been verified and use the same "
                      "checkers that produced a 57.6\\% rejection rate on "
                      "SkillBench; its column is therefore an upper bound."),
                align="lrrr")

    # ---------------- B. boundary & facet ----------------
    gh_all = fv[fv.corpus == "wildskills"].copy()
    sb_all = fv[fv.corpus == "skillbench"].copy()
    sb_all["boundary"] = sb_all["boundary_claimed"]
    sb_all["l2"] = sb_all["l2_claimed"]
    sb_all["facet"] = sb_all.apply(
        lambda r: r["facet"] if r["verdict"] != "mislabeled" else None, axis=1)
    order_cols = [("GitHub (unverified)", gh_all),
                  ("SkillBench (as audited)", sb_all),
                  ("SkillBench (verified)", kept_sb)]
    rows = []
    for b in BOUNDARY_ORDER:
        row = [b]
        for _, sub in order_cols:
            n = int((sub.boundary == b).sum())
            row += [n, f"{100 * n / len(sub):.1f}%"]
        rows.append(row)
    write_table("table3_boundary_verified",
                ["Artifact boundary"] + sum(
                    [[f"{l} (n)", f"{l} (%)"] for l, _ in order_cols], []),
                rows,
                caption=("Artifact-boundary mix before and after verifying the "
                         "SkillBench findings."),
                label="tab:rq1-verified-boundary",
                align="l" + "r" * 6)

    # ---- taxonomy level 2 (the inconsistency type) ----
    L2_ORDER = [x for x in kept_sb.l2.value_counts().index
                if x and x != "nan"]
    for x in gh_all.l2.value_counts().index:
        if x and x != "nan" and x not in L2_ORDER:
            L2_ORDER.append(x)
    rows = []
    for l2 in L2_ORDER:
        row = [l2]
        for _, sub in order_cols:
            n = int((sub.l2 == l2).sum())
            row += [n, f"{100 * n / len(sub):.1f}%"]
        rows.append(row)
    write_table("table4_l2_verified",
                ["Level-2 type"] + sum(
                    [[f"{l} (n)", f"{l} (%)"] for l, _ in order_cols], []),
                rows,
                caption=("Distribution of inconsistencies over the taxonomy "
                         "level-2 types, before and after verifying the "
                         "SkillBench findings."),
                label="tab:rq1-verified-l2",
                align="l" + "r" * 6, size=r"\footnotesize")

    FACET_DISPLAY = {"environment": "environment assumption", "capability": "capability",
                     "concept": "shared concept", "interface": "interface / schema",
                     "workflow": "workflow", "parameter": "parameter",
                     "return": "return value", "constraint": "constraint / exception",
                     "resource": "external resource", "dependency": "dependency version",
                     "service_contract": "external service contract",
                     "side_effect": "side effect", "fault_tolerance": "fault tolerance",
                     "semantic": "semantic (unclassified)"}
    facets = [x for x in fv.facet.value_counts().index if x in FACET_DISPLAY]
    rows = []
    for fac in facets:
        row = [FACET_DISPLAY[fac]]
        for _, sub in order_cols:
            n = int((sub.facet == fac).sum())
            row += [n, f"{100 * n / len(sub):.1f}%"]
        rows.append(row)
    write_table("table5_facet_verified",
                ["Contract element"] + sum(
                    [[f"{l} (n)", f"{l} (%)"] for l, _ in order_cols], []),
                rows,
                caption=("Contract element violated, before and after verifying "
                         "the SkillBench findings."),
                label="tab:rq1-verified-facet",
                align="l" + "r" * 6, size=r"\scriptsize")

    # ---------------- C. impact ----------------
    rows = []
    for lbl, sub in order_cols:
        n = len(sub)
        rows.append([lbl, n,
                     int(sub.blocks_execution.sum()),
                     f"{100 * sub.blocks_execution.mean():.1f}%",
                     int(sub.silent_error.sum()),
                     f"{100 * sub.silent_error.mean():.1f}%"])
    write_table("table2_impact_verified",
                ["Corpus", "Findings", "Blocks execution", "Share",
                 "Silent error", "Share"],
                rows,
                caption=("Agent impact before and after verifying the SkillBench "
                         "findings."),
                label="tab:rq1-verified-impact",
                align="lrrrrr")

    # ---------------- D. co-occurrence ----------------
    def pres(sub):
        m = defaultdict(set)
        for _, r in sub.iterrows():
            m[r.skill].add(r.boundary)
        return m

    rows = []
    for i in BOUNDARY_ORDER:
        row = [f"P(j | i), i = {i}"]
        for lbl, sub in order_cols[:1] + order_cols[2:]:
            m = pres(sub)
            a = {k for k, v in m.items() if i in v}
            other = [b for b in BOUNDARY_ORDER if b != i]
            vals = []
            for j in other:
                b_ = {k for k, v in m.items() if j in v}
                vals.append(len(a & b_) / len(a) if a else float("nan"))
            row.append(" / ".join(f"{x:.2f}" for x in vals))
        rows.append(row)
    write_table("table6_cooccurrence_verified",
                ["Condition (order: the other two boundaries)"] +
                ["GitHub (unverified)", "SkillBench (verified)"],
                rows,
                caption=("Cross-boundary co-occurrence $P(j \\mid i)$ at the "
                         "artifact-boundary level, GitHub as audited vs SkillBench "
                         "after verification."),
                label="tab:rq1-verified-cooccurrence",
                align="lrr", raw_header=True)

    def multi(sub_skills, findings):
        m = pres(findings)
        n_with = len(m)
        two = sum(1 for v in m.values() if len(v) >= 2)
        three = sum(1 for v in m.values() if len(v) >= 3)
        return {"with_findings": n_with, "ge2": two, "all3": three,
                "ge2_pct": 100 * two / n_with if n_with else 0,
                "all3_pct": 100 * three / n_with if n_with else 0}

    summary["multi_boundary"] = {
        "GitHub (unverified)": multi(gh_skills, fv[fv.corpus == "wildskills"]),
        "SkillBench (as audited)": multi(sb_skills, fv[fv.corpus == "skillbench"]),
        "SkillBench (verified)": multi(sb_skills, kept_sb),
    }

    # ---------------- F. skill composition (doc-only vs with artifacts) ----
    write_composition_table(s)

    # ---------------- E. combined L1 + L2 taxonomy table ----------------
    write_taxonomy_table(gh_all, kept_sb)

    json.dump(summary, open(os.path.join(VOUT, "summary.json"), "w"),
              ensure_ascii=False, indent=1)

    print("\nprevalence / density")
    for k, x in A.items():
        print(f"  {k:34s} n={x['n_skills']} prev={x['prevalence']:.1f}% "
              f"total={x['total']} mean={x['mean']:.2f} med={x['median']:.0f} "
              f"p90={x['p90']:.0f} dens={x['dens_median']:.2f}")
    print("\nboundary mix")
    for lbl, sub in order_cols:
        c = Counter(sub.boundary)
        t = len(sub)
        print(f"  {lbl:34s} " + "  ".join(
            f"{b.split(chr(8211))[-1]}={100 * c.get(b, 0) / t:.1f}%" for b in BOUNDARY_ORDER))
    print("\nmulti-boundary")
    for k, x in summary["multi_boundary"].items():
        print(f"  {k:34s} >=2: {x['ge2']}/{x['with_findings']} "
              f"({x['ge2_pct']:.1f}%)  all3: {x['all3']} ({x['all3_pct']:.1f}%)")




# --------------------------------------------------------------------------
# combined level-1 + level-2 taxonomy table
# --------------------------------------------------------------------------
L1_ORDER = BOUNDARY_ORDER
L1_OF = {b: l1 for l1, b in BOUNDARY.items()}


def write_taxonomy_table(gh, sb):
    """One grouped table: artifact boundary (L1) > inconsistency type (L2).

    Structure is carried by booktabs rules (a trimmed rule above each subtotal)
    rather than by bold/italic, so the table renders identically in any font
    setup and stays compact.
    """
    def n(col, t):
        return int((col.l2 == t).sum())

    def pc(col, t):
        return 100 * (col.l2 == t).mean() if len(col) else 0.0

    total_gh, total_sb = len(gh), len(sb)
    groups, csv_rows = [], []
    for l1 in ("implementation", "document", "environmental"):
        b = BOUNDARY[l1]
        types = [t for t in (set(gh.l2) | set(sb.l2))
                 if TYPE_L1.get(t) == l1 and (n(gh, t) + n(sb, t)) > 0]
        types.sort(key=lambda t: (-n(gh, t), -n(sb, t)))   # as in Table 4
        if types:
            groups.append((b, types))
            for t in types:
                csv_rows.append([b, t, n(gh, t), round(pc(gh, t), 1),
                                 n(sb, t), round(pc(sb, t), 1), "type"])
            gh_sub = sum(n(gh, t) for t in types)
            sb_sub = sum(n(sb, t) for t in types)
            csv_rows.append([b, "subtotal", gh_sub,
                             round(100 * gh_sub / total_gh, 1), sb_sub,
                             round(100 * sb_sub / total_sb, 1), "subtotal"])

    def th(k):
        return f"{k:,}".replace(",", "{,}")

    body = []
    for gi, (b, types) in enumerate(groups):
        span = len(types) + 1
        for k, t in enumerate(types):
            first = (r"\multirow{%d}{*}{%s}" % (span, tex_escape(b))
                     if k == 0 else "")
            body.append("    %s & %s & %s & %s \\\\" % (
                first, tex_escape(t),
                f"{n(gh, t)} ({pc(gh, t):.1f}\\%)",
                f"{n(sb, t)} ({pc(sb, t):.1f}\\%)"))
        body.append(r"    \cmidrule(lr){2-4}")
        gh_sub = sum(n(gh, t) for t in types)
        sb_sub = sum(n(sb, t) for t in types)
        body.append("     & subtotal & %s (%.1f\\%%) & %s (%.1f\\%%) \\\\"
                    % (th(gh_sub), 100 * gh_sub / total_gh,
                       th(sb_sub), 100 * sb_sub / total_sb))
        if gi != len(groups) - 1:
            body.append(r"    \addlinespace[4pt]")

    tex = "\n".join([
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Distribution of contract inconsistencies over the taxonomy, "
        r"combining the artifact boundary (level 1) and the inconsistency type "
        r"(level 2). GitHub findings are unverified; SkillBench uses the verified "
        r"subset.}",
        r"  \label{tab:rq1-taxonomy-distribution}",
        r"  \footnotesize",
        r"  \setlength{\tabcolsep}{5pt}",
        r"  \resizebox{\ifdim\width>\linewidth \linewidth\else\width\fi}{!}{%",
        r"  \begin{tabular}{l l r r}",
        r"    \toprule",
        r"    Artifact boundary (L1) & Inconsistency type (L2) & GitHub (unverified)"
        r" & SkillBench (verified) \\",
        r"    \midrule",
    ] + body + [
        r"    \midrule",
        r"    \multicolumn{2}{l}{Total} & %s (100.0\%%) & %s (100.0\%%) \\"
        % (th(total_gh), th(total_sb)),
        r"    \bottomrule",
        r"  \end{tabular}",
        r"  }%",
        r"",
        r"  \vspace{2pt}",
        r"  \begin{minipage}{\linewidth}",
        r"    \footnotesize\raggedright Each type is listed under the boundary at "
        r"which the contract breaks; the rule marks where the types of a boundary "
        r"end and its subtotal begins. Shares are within each corpus and may not "
        r"sum exactly because of rounding.",
        r"  \end{minipage}",
        r"\end{table}",
        "",
    ])
    open(os.path.join(VOUT, "table7_taxonomy_l1_l2.tex"), "w",
         encoding="utf-8").write(tex)
    with open(os.path.join(VOUT, "table7_taxonomy_l1_l2.csv"), "w", newline="",
              encoding="utf-8") as fh:
        import csv as _csv
        w = _csv.writer(fh)
        w.writerow(["boundary_l1", "type_l2", "github_n", "github_pct",
                    "skillbench_verified_n", "skillbench_verified_pct", "row"])
        w.writerows(csv_rows)
    print("  table -> outputs/verified/table7_taxonomy_l1_l2.csv/.tex")


TYPE_L1 = {
    "over_promised": "implementation",
    "semantic_conflict": "implementation",
    "under_promised": "implementation",
    "interface_contract_mismatch": "document",
    "shared_concept_definition_conflict": "document",
    "cross_document_process_conflict": "document",
    "external_resource_invalid": "environmental",
    "dependency_version_drift": "environmental",
    "external_service_contract_change": "environmental",
    "environment_fact_conflict": "environmental",
}


def write_composition_table(s):
    """How many skills are documentation-only vs ship other artifacts."""
    import pandas as _pd
    s = s.copy()
    for c in ("n_files", "n_doc_files"):
        s[c] = _pd.to_numeric(s[c], errors="coerce").fillna(0)
    s["doc_only"] = s.n_files <= s.n_doc_files

    order = [("wildskills", "GitHub Skills (unverified)"),
             ("skillbench", "SkillBench")]
    rows, csv_rows = [], []
    tot_d = tot_a = 0
    for key, label in order:
        g = s[s.corpus == key]
        d, a = int(g.doc_only.sum()), int((~g.doc_only).sum())
        tot_d += d
        tot_a += a
        rows.append([label, f"{d} ({100 * d / len(g):.1f}\\%)",
                     f"{a} ({100 * a / len(g):.1f}\\%)", f"{len(g)}"])
        csv_rows.append([label, d, round(100 * d / len(g), 1), a,
                         round(100 * a / len(g), 1), len(g)])
    n = len(s)
    rows.append(["Total", f"{tot_d} ({100 * tot_d / n:.1f}\\%)",
                 f"{tot_a} ({100 * tot_a / n:.1f}\\%)", f"{n}"])
    csv_rows.append(["Total", tot_d, round(100 * tot_d / n, 1), tot_a,
                     round(100 * tot_a / n, 1), n])

    L_ = [r"\begin{table}[t]", r"  \centering",
          r"  \caption{Composition of the two corpora by what a skill ships. "
          r"A skill is documentation-only when its directory contains no "
          r"file other than documentation; otherwise it ships artifacts "
          r"(scripts, configuration, resources).}",
          r"  \label{tab:rq1-composition}", r"  \small",
          r"  \setlength{\tabcolsep}{5pt}",
          r"  \begin{tabular}{l r r r}", r"    \toprule",
          r"    Corpus & Documentation-only & With artifacts & Total \\",
          r"    \midrule"]
    for row in rows[:-1]:
        L_.append("    " + " & ".join(row) + r" \\")
    L_ += [r"    \midrule", "    " + " & ".join(rows[-1]) + r" \\",
           r"    \bottomrule", r"  \end{tabular}",
           r"", r"  \vspace{2pt}",
           r"  \begin{minipage}{\linewidth}",
           r"    \footnotesize\raggedright Shares (in parentheses) are within "
           r"each corpus.",
           r"  \end{minipage}", r"\end{table}", ""]
    open(os.path.join(VOUT, "table8_skill_composition.tex"), "w",
         encoding="utf-8").write("\n".join(L_))
    with open(os.path.join(VOUT, "table8_skill_composition.csv"), "w",
              newline="", encoding="utf-8") as fh:
        import csv as _csv
        w = _csv.writer(fh)
        w.writerow(["corpus", "doc_only_n", "doc_only_pct", "with_artifacts_n",
                    "with_artifacts_pct", "total"])
        w.writerows(csv_rows)
    print("  table -> outputs/verified/table8_skill_composition.csv/.tex")


if __name__ == "__main__":
    main()
