"""
RQ1-A  Prevalence and density.

Answers
  * How prevalent?  share of skills with >=1 inconsistency, per-skill count,
    mean, median, P90 (plus max and IQR for completeness).
  * How dense?      inconsistencies per 100 contract claims (primary), with
    per-100-documentation-claim and per-100-LOC as fallbacks.

Outputs
  outputs/table1_prevalence.{csv,tex}
  outputs/table2_severity_impact.{csv,tex}
  outputs/fig2_count_distribution.csv
  outputs/rq1_stats.json

Run:  python3 analyze_prevalence.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rq1_lib as L  # noqa: E402


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def fmt(x: float, nd: int = 2) -> str:
    return f"{x:.0f}" if float(x).is_integer() else f"{x:.{nd}f}"


def main() -> None:
    s = pd.read_csv(os.path.join(L.OUT, "rq1_skills.csv"))
    f = pd.read_csv(os.path.join(L.OUT, "rq1_findings.csv"))
    for c in ("n_findings", "contract_claims", "doc_claims", "code_claims",
              "code_loc", "doc_lines", "n_blocking", "n_silent"):
        s[c] = num(s[c])

    stats: dict = {}
    table_rows: list[list] = []
    counts_rows: list[list] = []
    sev_rows: list[list] = []

    cols = [c.label for c in L.CORPORA]
    metrics: dict[str, dict[str, str]] = {}

    for corpus in L.CORPORA:
        g = s[s.corpus == corpus.key].copy()
        n = len(g)
        prev = int((g.n_findings > 0).sum())
        nf = int(g.n_findings.sum())
        d_claims = g.loc[g.contract_claims > 0, "n_findings"] / \
            g.loc[g.contract_claims > 0, "contract_claims"] * 100
        d_doc = g.loc[g.doc_claims > 0, "n_findings"] / \
            g.loc[g.doc_claims > 0, "doc_claims"] * 100
        hc = g[g.code_loc > 0]
        d_loc = hc.n_findings / hc.code_loc * 100

        stats[corpus.key] = {
            "label": corpus.label,
            "n_skills": n,
            "n_with_findings": prev,
            "prevalence": prev / n,
            "n_findings": nf,
            "mean": float(g.n_findings.mean()),
            "median": float(g.n_findings.median()),
            "p90": float(np.percentile(g.n_findings, 90)),
            "p99": float(np.percentile(g.n_findings, 99)),
            "max": int(g.n_findings.max()),
            "iqr": [float(g.n_findings.quantile(.25)),
                    float(g.n_findings.quantile(.75))],
            "n_zero": int((g.n_findings == 0).sum()),
            "claims_total": int(g.contract_claims.sum()),
            "claims_median": float(g.contract_claims.median()),
            "doc_claims_median": float(g.doc_claims.median()),
            "density_claims_median": float(d_claims.median()),
            "density_claims_mean": float(d_claims.mean()),
            "density_claims_iqr": [float(d_claims.quantile(.25)),
                                   float(d_claims.quantile(.75))],
            "density_claims_pooled": nf / g.contract_claims.sum() * 100,
            "density_doc_median": float(d_doc.median()),
            "density_doc_pooled": nf / g.doc_claims.sum() * 100,
            "n_with_code": int(len(hc)),
            "density_loc_median": float(d_loc.median()),
            "density_loc_mean": float(d_loc.mean()),
            "density_loc_pooled": hc.n_findings.sum() / hc.code_loc.sum() * 100,
            "code_loc_median_all": float(g.code_loc.median()),
            "blocking": int(g.n_blocking.sum()),
            "silent": int(g.n_silent.sum()),
        }
        # count distribution for Figure 2 (absolute + share, identical bins)
        dist = g.n_findings.value_counts().sort_index()
        for k, v in dist.items():
            counts_rows.append([corpus.label, int(k), int(v), round(100 * v / n, 2)])

        for sev, key in (("critical", "n_critical"), ("high", "n_high"),
                         ("medium", "n_medium"), ("low", "n_low")):
            g[key] = num(g[key])
            sev_rows.append([corpus.label, sev.capitalize(),
                             int(g[key].sum())])

        metrics.setdefault("Skills audited", {})[corpus.label] = f"{n}"
        metrics.setdefault("Skills with at least one inconsistency", {})[corpus.label] = \
            f"{prev} ({100 * prev / n:.1f}%)"
        metrics.setdefault("Total inconsistencies", {})[corpus.label] = f"{nf}"
        metrics.setdefault("Mean per skill", {})[corpus.label] = f"{g.n_findings.mean():.2f}"
        metrics.setdefault("Median per skill", {})[corpus.label] = f"{fmt(g.n_findings.median())}"
        metrics.setdefault("P90 per skill", {})[corpus.label] = f"{fmt(np.percentile(g.n_findings, 90))}"
        metrics.setdefault("Max per skill", {})[corpus.label] = f"{int(g.n_findings.max())}"
        metrics.setdefault("Skills with zero findings", {})[corpus.label] = \
            f"{int((g.n_findings == 0).sum())} ({100 * (g.n_findings == 0).mean():.1f}%)"
        metrics.setdefault("Median contract claims / skill", {})[corpus.label] = \
            f"{g.contract_claims.median():.0f}"
        metrics.setdefault("Inconsistencies per 100 contract claims (median skill)", {})[corpus.label] = \
            f"{d_claims.median():.2f}"
        metrics.setdefault("Inconsistencies per 100 contract claims (pooled)", {})[corpus.label] = \
            f"{nf / g.contract_claims.sum() * 100:.2f}"
        metrics.setdefault("Skills shipping code", {})[corpus.label] = \
            f"{len(hc)} ({100 * len(hc) / n:.1f}%)"
        metrics.setdefault("Inconsistencies per 100 LOC (median, code-bearing skills)", {})[corpus.label] = \
            f"{d_loc.median():.2f}"

    # ---- complete metric grid on the union of keys, in insertion order ----
    for k, v in metrics.items():
        table_rows.append([k] + [v.get(c, "-") for c in cols])

    L.write_table(
        "table1_prevalence",
        ["Metric"] + cols,
        table_rows,
        caption=("Prevalence and density of contract inconsistencies in the two "
                 "corpora. Density is normalised by the number of contract claims "
                 "extracted from each skill (documentation statements plus declared "
                 "code-interface elements)."),
        label="tab:rq1-prevalence",
        note=("Values in parentheses are shares of the corpus. "
              "``Pooled'' weights every inconsistency equally; the median-skill "
              "figure weights every skill equally."),
        align="l" + "r" * len(cols),
    )

    # ---- severity / agent impact ----
    imp_rows = []
    for corpus in L.CORPORA:
        g = s[s.corpus == corpus.key].copy()
        nf = int(g.n_findings.sum())
        imp_rows.append([corpus.label, "Critical", int(g.n_critical.sum()),
                         f"{100 * g.n_critical.sum() / nf:.1f}%"])
        imp_rows.append([corpus.label, "High", int(g.n_high.sum()),
                         f"{100 * g.n_high.sum() / nf:.1f}%"])
        imp_rows.append([corpus.label, "Medium", int(g.n_medium.sum()),
                         f"{100 * g.n_medium.sum() / nf:.1f}%"])
        imp_rows.append([corpus.label, "Low", int(g.n_low.sum()),
                         f"{100 * g.n_low.sum() / nf:.1f}%"])
        imp_rows.append([corpus.label, "Confirmed to block execution",
                         int(g.n_blocking.sum()),
                         f"{100 * g.n_blocking.sum() / nf:.1f}%"])
        imp_rows.append([corpus.label, "Produce silent errors",
                         int(g.n_silent.sum()),
                         f"{100 * g.n_silent.sum() / nf:.1f}%"])
    L.write_table(
        "table2_severity_impact",
        ["Corpus", "Category", "Findings", "Share of findings"],
        imp_rows,
        caption=("Severity and agent-impact profile of the confirmed "
                 "inconsistencies."),
        label="tab:rq1-severity",
        note=("A finding is *silent* when the agent-visible outcome is wrong "
              "without an observable failure signal."),
        align="llrr",
    )

    pd.DataFrame(counts_rows, columns=["corpus", "n_inconsistencies",
                                       "n_skills", "share_pct"]).to_csv(
        os.path.join(L.OUT, "fig2_count_distribution.csv"), index=False)
    print("  data   -> outputs/fig2_count_distribution.csv")
    json.dump(stats, open(os.path.join(L.OUT, "rq1_stats.json"), "w"),
              indent=1)
    print("  stats  -> outputs/rq1_stats.json")

    # ---- console summary ----
    for k, v in stats.items():
        print(f"\n[{v['label']}] n={v['n_skills']} prevalence={100 * v['prevalence']:.1f}% "
              f"findings={v['n_findings']}")
        print(f"   per skill: mean={v['mean']:.2f} median={v['median']:.1f} "
              f"P90={v['p90']:.0f} max={v['max']}")
        print(f"   density per 100 claims: median={v['density_claims_median']:.2f} "
              f"pooled={v['density_claims_pooled']:.2f} | "
              f"per 100 LOC (code-bearing) median={v['density_loc_median']:.2f}")
        print(f"   blocking={v['blocking']} silent={v['silent']}")


if __name__ == "__main__":
    main()
