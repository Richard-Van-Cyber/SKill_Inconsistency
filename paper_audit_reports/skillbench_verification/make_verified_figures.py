"""
Regenerate RQ1 Figures 2 and 3 on the verified SkillBench basis.

  figures/fig2_count_distribution_verified    inconsistency count per skill
  figures/fig3_artifact_boundary_verified     artifact-boundary mix

GitHub is drawn with a hatched pattern to mark it as UNVERIFIED.

Run:  python3 make_verified_figures.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "rq1_analysis"))
import rq1_lib as L  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

L.apply_style()
import matplotlib.pyplot as plt  # noqa: E402

GH = L.CORPUS_BY_KEY["wildskills"].color      # GitHub: unverified
SB = L.CORPUS_BY_KEY["skillbench"].color      # SkillBench: verified
BOUNDARY_ORDER = ["Document\u2013Code", "Document\u2013Document",
                  "Skill\u2013Environment"]

# Compact axis labels for the level-2 types: every audit type name ends in
# _conflict / _mismatch / _drift / _invalid / _change / _promised, so only the
# distinguishing part is kept on the axis and the full slugs go in the caption.
L2_SHORT = {
    "over_promised": "Over-promised",
    "environment_fact_conflict": "Environment",
    "shared_concept_definition_conflict": "Concept definition",
    "interface_contract_mismatch": "Interface",
    "semantic_conflict": "Semantic",
    "cross_document_process_conflict": "Cross-doc process",
    "external_resource_invalid": "External resource",
    "external_service_contract_change": "Service contract",
    "dependency_version_drift": "Dependency",
    "under_promised": "Under-promised",
}


def save(fig, stem):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(FIG, f"{stem}.{ext}"))
    plt.close(fig)
    print(f"  figure -> figures/{stem}.pdf / .png")


def load():
    fv = pd.read_csv(os.path.join(OUT, "verified", "rq1_findings_verified.csv"))
    s = pd.read_csv(os.path.join(
        os.path.dirname(HERE), "rq1_analysis", "outputs", "rq1_skills.csv"))
    return fv, s


def fig2(fv, s) -> None:
    gh = s[s.corpus == "wildskills"]
    sb = s[s.corpus == "skillbench"]
    sb_kept = fv[(fv.corpus == "skillbench") & fv.kept].groupby("skill").size()
    sb_counts = pd.Series([int(sb_kept.get(x, 0)) for x in sb.skill])
    xmax = int(max(gh.n_findings.max(), sb_counts.max()))
    xs = np.arange(0, xmax + 1)

    fig, ax = plt.subplots(figsize=(3.45, 2.25))
    gh_share = [100 * (gh.n_findings == x).mean() for x in xs]
    sb_share = [100 * (sb_counts == x).mean() for x in xs]
    w = 0.40
    ax.bar(xs - w / 2, gh_share, width=w, color=GH, alpha=0.42,
           edgecolor=GH, hatch="///", linewidth=0.0, zorder=2,
           label=f"GitHub Skills($n$={len(gh)})")
    ax.bar(xs + w / 2, sb_share, width=w, color=SB, alpha=0.95,
           edgecolor="white", linewidth=0.4, zorder=3,
           label=f"SkillBench Skills($n$={len(sb)})")

    ax.set_xlabel("Confirmed inconsistencies per skill")
    ax.set_ylabel("Share of skills (%)")
    ax.set_xlim(-0.7, xmax + 0.7)
    ax.set_xticks(range(0, xmax + 1, 2))
    ax.legend(loc="upper right", handlelength=1.2, borderpad=0.2, fontsize=6.6)
    ax.grid(axis="y", linewidth=0.35, alpha=0.35)
    ax.set_axisbelow(True)
    save(fig, "fig2_count_distribution_verified")


def fig3(fv) -> None:
    gh = fv[fv.corpus == "wildskills"]
    sb = fv[(fv.corpus == "skillbench") & fv.kept]
    y = np.arange(len(BOUNDARY_ORDER))
    h = 0.36
    fig, ax = plt.subplots(figsize=(3.45, 1.95))
    for k, (sub, color, hatch, label) in enumerate([
            (gh, GH, "///", "GitHub Skills, unverified"),
            (sb, SB, "", "SkillBench, verified")]):
        vals = [100 * (sub.boundary == b).mean() for b in BOUNDARY_ORDER]
        cnts = [int((sub.boundary == b).sum()) for b in BOUNDARY_ORDER]
        bars = ax.barh(y + (k - 0.5) * h, vals, height=h, color=color,
                       alpha=0.42 if hatch else 0.95, edgecolor=color,
                       hatch=hatch, linewidth=0.0 if hatch else 0.4,
                       label=label, zorder=3)
        for b, v, n in zip(bars, vals, cnts):
            ax.text(v + 0.8, b.get_y() + b.get_height() / 2,
                    f"{v:.1f}%  ({n})", va="center", ha="left", fontsize=6.3)
    ax.set_yticks(y)
    ax.set_yticklabels(BOUNDARY_ORDER)
    ax.invert_yaxis()
    ax.set_xlabel("Share of inconsistencies (%)")
    ax.set_xlim(0, 70)
    ax.set_xticks(range(0, 61, 20))
    ax.grid(axis="x", linewidth=0.35, alpha=0.35)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=2,
              handlelength=1.2, borderpad=0.2, columnspacing=1.4, fontsize=7)
    save(fig, "fig3_artifact_boundary_verified")


def fig4(fv) -> None:
    """Taxonomy level-2 (inconsistency type) distribution."""
    gh = fv[fv.corpus == "wildskills"]
    sb = fv[(fv.corpus == "skillbench") & fv.kept]
    gh_sh = gh.l2.value_counts(normalize=True) * 100
    sb_sh = sb.l2.value_counts(normalize=True) * 100
    order = sorted(set(gh_sh.index) | set(sb_sh.index),
                   key=lambda x: -gh_sh.get(x, 0))
    gh_v = [gh_sh.get(x, 0) for x in order]
    sb_v = [sb_sh.get(x, 0) for x in order]
    y = np.arange(len(order))
    h = 0.38

    fig, ax = plt.subplots(figsize=(3.45, 2.9))
    bars = ax.barh(y - h / 2, gh_v, height=h, color=GH, alpha=0.42,
                   edgecolor=GH, hatch="///", linewidth=0.0, zorder=3,
                   label="GitHub Skills, unverified")
    for b, v in zip(bars, gh_v):
        if v > 0:
            ax.text(v + 0.6, b.get_y() + b.get_height() / 2, f"{v:.1f}",
                    va="center", ha="left", fontsize=6.0)
    bars = ax.barh(y + h / 2, sb_v, height=h, color=SB, alpha=0.95,
                   edgecolor="white", linewidth=0.4, zorder=3,
                   label="SkillBench, verified")
    for b, v in zip(bars, sb_v):
        ax.text(v + 0.6, b.get_y() + b.get_height() / 2,
                f"{v:.1f}" if v > 0 else "0", va="center", ha="left",
                fontsize=6.0)

    ax.set_yticks(y)
    ax.set_yticklabels([L2_SHORT.get(x, x) for x in order], fontsize=7.4)
    ax.invert_yaxis()
    ax.set_xlabel("Share of inconsistencies (%)")
    ax.set_xlim(0, max(max(gh_v), max(sb_v)) * 1.22)
    ax.grid(axis="x", linewidth=0.35, alpha=0.35)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", pad=1.5)
    ax.legend(loc="lower right", handlelength=1.2, borderpad=0.2, fontsize=7)
    save(fig, "fig4_l2_types_verified")


DOC_C = "#B8C4D9"      # documentation-only
ART_C = "#35597F"      # ships artifacts


def _counts(fv, s):
    """Per-skill inconsistency counts plus the documentation-only flag."""
    k = fv[(fv.corpus == "skillbench") & fv.kept].groupby("skill").size()
    out = {}
    for corpus, col in (("wildskills", "n_findings"), ("skillbench", None)):
        g = s[s.corpus == corpus].copy()
        g["n"] = (pd.to_numeric(g[col], errors="coerce").fillna(0).astype(int)
                  if col else [int(k.get(x, 0)) for x in g.skill])
        g["doc_only"] = (pd.to_numeric(g.n_files, errors="coerce").fillna(0)
                         <= pd.to_numeric(g.n_doc_files, errors="coerce").fillna(0))
        out[corpus] = g
    return out


def fig5(fv, s) -> None:
    """Inconsistency-count distribution: documentation-only vs skills with artifacts.

    Both corpora are pooled into a single panel; only the two skill kinds are
    distinguished.  The pooled counts are dominated by the (unverified) GitHub
    corpus, so the per-corpus split is reported separately in the results doc.
    """
    data = _counts(fv, s)
    pool = pd.concat([data["wildskills"], data["skillbench"]], ignore_index=True)
    xmax = int(pool.n.max())
    xs = np.arange(0, xmax + 1)

    fig, ax = plt.subplots(figsize=(3.45, 2.30))
    for sub, color, width, hatch, label in (
            (pool[pool.doc_only], DOC_C, 0.88, "///",
             f"documentation-only ($n$={int(pool.doc_only.sum())})"),
            (pool[~pool.doc_only], ART_C, 0.44, "",
             f"with artifacts ($n$={int((~pool.doc_only).sum())})")):
        share = [100 * (sub.n == x).mean() for x in xs]
        ax.bar(xs, share, width=width, color=color, alpha=0.95,
               edgecolor=ART_C if hatch else "white", hatch=hatch,
               linewidth=0.0 if hatch else 0.4, zorder=3, label=label)

    ax.set_xlabel("Confirmed inconsistencies per skill")
    ax.set_ylabel("Share of skills (%)")
    ax.set_xlim(-0.7, xmax + 0.7)
    ax.set_xticks(range(0, xmax + 1, 3))
    ax.set_ylim(0, 44)
    ax.grid(axis="y", linewidth=0.35, alpha=0.35)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=6.8, handlelength=1.2, borderpad=0.25,
              labelspacing=0.35, borderaxespad=0.3)

    save(fig, "fig5_doconly_vs_artifacts")


if __name__ == "__main__":
    fv, s = load()
    fig2(fv, s)
    fig3(fv)
    fig4(fv)
    fig5(fv, s)
