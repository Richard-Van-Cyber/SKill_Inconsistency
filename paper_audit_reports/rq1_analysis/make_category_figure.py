"""
RQ1 category figure -- inconsistency prevalence by Skill category, both corpora.

  figures/fig_category_distribution   dumbbell: one row per category, the two
                                      corpora at the two ends, 95% Wilson CI as
                                      a light interval behind each dot.

Run:  MPLCONFIGDIR=/tmp/mplcache python3 make_category_figure.py
"""
from __future__ import annotations

import csv
import math
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rq1_lib as L  # noqa: E402

L.apply_style()
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

GH = L.CORPUS_BY_KEY["wildskills"].color
SB = L.CORPUS_BY_KEY["skillbench"].color

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VER = os.path.join(ROOT, "skillbench_verification", "outputs", "verified",
                   "rq1_findings_verified.csv")

SHORT = {
    "software-engineering": "software engineering",
    "media-content-production": "media",
    "office-white-collar": "office",
    "finance-economics": "finance",
    "natural-science": "natural science",
    "industrial-physical-systems": "industrial",
    "cybersecurity": "cybersecurity",
    "mathematics-or-formal-reasoning": "math / formal",
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h) * 100, min(1.0, c + h) * 100


def load() -> pd.DataFrame:
    kept = Counter()
    with open(VER) as fh:
        for r in csv.DictReader(fh):
            if r["verdict"] in ("confirmed", "mislabeled"):
                kept[r["skill"]] += 1
    s = pd.read_csv(os.path.join(L.OUT, "rq1_skills.csv"))
    s["corpus"] = np.where(s.corpus.astype(str).str.startswith("skillbench"),
                           "skillbench", "github")
    s["n_used"] = np.where(s.corpus == "skillbench",
                           s.skill.map(lambda x: kept.get(x, 0)),
                           s.n_findings.fillna(0)).astype(int)
    return s


def summarise(s: pd.DataFrame, corpus: str) -> pd.DataFrame:
    g = s[s.corpus == corpus]
    rows = []
    for dom, d in g.groupby("domain"):
        n = len(d)
        k = int((d.n_used > 0).sum())
        lo, hi = wilson(k, n)
        claims = int(d.contract_claims.fillna(0).sum())
        rows.append(dict(domain=dom, n=n, k=k, prev=100 * k / n, lo=lo, hi=hi,
                         density=100 * d.n_used.sum() / claims if claims else 0.0))
    return pd.DataFrame(rows)


def main() -> None:
    s = load()
    sb, gh = summarise(s, "skillbench"), summarise(s, "github")
    j = sb.merge(gh, on="domain", suffixes=("_sb", "_gh"))
    j = j.sort_values("prev_sb").reset_index(drop=True)

    pooled_sb = 100 * s[s.corpus == "skillbench"].n_used.gt(0).sum() / \
        (s.corpus == "skillbench").sum()
    pooled_gh = 100 * s[s.corpus == "github"].n_used.gt(0).sum() / \
        (s.corpus == "github").sum()

    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    h, gap = 0.36, 0.30

    for i, r in j.iterrows():
        y_sb, y_gh = i * (2 * h + gap), i * (2 * h + gap) + h
        ax.barh(y_sb, r.prev_sb, height=h, color=SB, zorder=3,
                edgecolor="white", linewidth=0.4)
        ax.barh(y_sb, r.hi_sb - r.lo_sb, left=r.lo_sb, height=h * 0.34,
                color=SB, alpha=0.30, zorder=2)
        ax.barh(y_gh, r.prev_gh, height=h, color=GH, zorder=3,
                edgecolor="white", linewidth=0.4)
        ax.barh(y_gh, r.hi_gh - r.lo_gh, left=r.lo_gh, height=h * 0.34,
                color=GH, alpha=0.30, zorder=2)
        ax.axhline(y_gh + h / 2 + gap / 2, color="black", lw=0.3,
                   alpha=0.13, zorder=0)

    ticks, labels = [], []
    for i, r in j.iterrows():
        ticks.append(i * (2 * h + gap) + h / 2)
        labels.append(f"{SHORT.get(r.domain, r.domain)}"
                      f"\n{int(r.n_sb)} / {int(r.n_gh)}")
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels, fontsize=5.3, linespacing=1.35)
    ax.set_ylim(-h - gap / 2, (len(j) - 1) * (2 * h + gap) + h + h / 2 + gap / 2)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 20, 40, 60, 80, 100])

    ax.set_xlabel("Skills with $\\geq$1 inconsistency (%)", fontsize=6)
    ax.tick_params(axis="x", labelsize=5.8)
    ax.tick_params(axis="y", length=0)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_axisbelow(True)

    ax.legend(handles=[
        Line2D([], [], color=SB, lw=4, label=f"SkillBench  ({pooled_sb:.0f}%)"),
        Line2D([], [], color=GH, lw=4, label=f"GitHub  ({pooled_gh:.0f}%)"),
    ], fontsize=5.4, loc="lower left", bbox_to_anchor=(0.0, 1.005), ncol=2,
        frameon=False, handlelength=1.1, borderaxespad=0.0,
        columnspacing=1.6, handletextpad=0.5)


    # ---- appendix table + LaTeX include ----
    tab = j[["domain", "n_sb", "k_sb", "prev_sb", "lo_sb", "hi_sb",
             "n_gh", "k_gh", "prev_gh", "lo_gh", "hi_gh"]].copy()
    tab.columns = ["domain", "n_sb", "k_sb", "prev_sb", "lo_sb", "hi_sb",
                   "n_gh", "k_gh", "prev_gh", "lo_gh", "hi_gh"]
    tab.to_csv(os.path.join(L.OUT, "table_category_distribution.csv"),
               index=False)

    def esc(t: str) -> str:
        return t.replace("_", "\\_").replace("&", "\\&").replace("%", "\\%")

    lines = [
        "% RQ1 -- inconsistency prevalence by Skill category (auto-generated)",
        "\\begin{table}[t]", "  \\centering", "  \\small",
        "  \\begin{tabular}{lrrrr}", "    \\toprule",
        "    & \\multicolumn{2}{c}{SkillBench} & \\multicolumn{2}{c}{GitHub} \\\\",
        "    \\cmidrule(lr){2-3}\\cmidrule(lr){4-5}",
        "    Category & $n$ & \\% & $n$ & \\% \\\\", "    \\midrule",
    ]
    for _, r in j.iloc[::-1].iterrows():
        lines.append(
            f"    {esc(SHORT.get(r.domain, r.domain))} & {int(r.n_sb)} & "
            f"{r.prev_sb:.0f} & {int(r.n_gh)} & {r.prev_gh:.0f} \\\\")
    lines += [
        "    \\midrule",
        f"    All & {int(j.n_sb.sum())} & {pooled_sb:.0f} & "
        f"{int(j.n_gh.sum())} & {pooled_gh:.0f} \\\\",
        "    \\bottomrule", "  \\end{tabular}",
        "  \\caption{Share of Skills carrying at least one contract "
        "inconsistency, by category and corpus.}",
        "  \\label{tab:rq1-category}", "\\end{table}", "",
    ]
    with open(os.path.join(L.OUT, "table_category_distribution.tex"), "w") as fh:
        fh.write("\n".join(lines))

    inc = [
        "% Figure: inconsistency prevalence by Skill category, both corpora",
        "\\begin{figure}[t]", "  \\centering",
        "  \\includegraphics[width=\\linewidth]"
        "{figures/fig_category_distribution.pdf}",
        "  \\caption{Share of Skills carrying at least one contract "
        "inconsistency, by category. Bars give the point estimate, the pale "
        "extension the 95\\% Wilson interval; each label lists the number of "
        "Skills in SkillBench and in GitHub. No category separates from the "
        "pooled rate in either corpus "
        f"(SkillBench {pooled_sb:.0f}\\%, GitHub {pooled_gh:.0f}\\%; "
        "$\\chi^2$ test $p=0.80$ and $p=0.20$).}",
        "  \\label{fig:rq1-category}", "\\end{figure}", "",
    ]
    with open(os.path.join(L.FIG, "fig_category_distribution.tex"), "w") as fh:
        fh.write("\n".join(inc))
    print("  table -> outputs/table_category_distribution.{csv,tex}")
    print("  include -> figures/fig_category_distribution.tex")

    fig.tight_layout(pad=0.15)
    L.save(fig, "fig_category_distribution")
    print(j[["domain", "n_sb", "prev_sb", "lo_sb", "hi_sb", "n_gh", "prev_gh"]]
          .round(1).to_string(index=False))
    try:
        from scipy.stats import chi2_contingency
        for c, g in (("skillbench", sb), ("github", gh)):
            chi2, p, dof, _ = chi2_contingency(
                [[int(r.k), int(r.n - r.k)] for _, r in g.iterrows()])
            print(f"{c}: chi2={chi2:.2f} dof={dof} p={p:.3f}")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
