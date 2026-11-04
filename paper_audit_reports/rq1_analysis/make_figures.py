"""
RQ1 figures (vector PDF for LaTeX + PNG for previewing).

  figures/fig2_count_distribution   inconsistency count, both corpora, one scale
  figures/fig3_artifact_boundary    where the contract breaks
  figures/fig4_contract_facets      which contract element breaks
  figures/fig5_cooccurrence         P(boundary_j | boundary_i) heat map

Run:  python3 make_figures.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rq1_lib as L  # noqa: E402

L.apply_style()
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

GH = L.CORPUS_BY_KEY["wildskills"].color
SB = L.CORPUS_BY_KEY["skillbench"].color


# --------------------------------------------------------------------------
def fig2_count_distribution() -> None:
    d = pd.read_csv(os.path.join(L.OUT, "fig2_count_distribution.csv"))
    s = pd.read_csv(os.path.join(L.OUT, "rq1_skills.csv"))
    xmax = int(s.n_findings.max())
    xs = np.arange(0, xmax + 1)

    fig, ax = plt.subplots(figsize=(3.45, 2.15))
    for corpus, width, alpha, z in (("wildskills", 0.86, 0.55, 2),
                                    ("skillbench", 0.42, 0.95, 3)):
        c = L.CORPUS_BY_KEY[corpus]
        sub = d[d.corpus == c.label].set_index("n_inconsistencies")
        y = [float(sub.share_pct.get(x, 0.0)) for x in xs]
        ax.bar(xs, y, width=width, color=c.color, alpha=alpha, zorder=z,
               edgecolor="white", linewidth=0.4,
               label=f"{c.label} ($n$={int(s[s.corpus == corpus].shape[0])})")

    ax.set_xlabel("Inconsistencies per skill")
    ax.set_ylabel("Share of skills (%)")
    ax.set_xlim(-0.7, xmax + 0.7)
    ax.set_xticks(range(0, xmax + 1, 2))
    ax.legend(loc="upper right", handlelength=1.1, borderpad=0.2)
    ax.grid(axis="y", linewidth=0.35, alpha=0.35)
    ax.set_axisbelow(True)

    lines = []
    for corpus in ("wildskills", "skillbench"):
        g = s[s.corpus == corpus]
        lines.append(f"{L.CORPUS_BY_KEY[corpus].label}: median {g.n_findings.median():.0f}, "
                     f"P90 {np.percentile(g.n_findings, 90):.0f}")
    ax.text(0.985, 0.60, "\n".join(lines), transform=ax.transAxes,
            ha="right", va="top", fontsize=6.6, linespacing=1.35,
            bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="0.75", lw=0.5))
    L.save(fig, "fig2_count_distribution")


# --------------------------------------------------------------------------
def fig3_artifact_boundary() -> None:
    d = pd.read_csv(os.path.join(L.OUT, "fig3_boundary.csv"))
    labels = [c.label for c in L.CORPORA]
    boundaries = list(d.boundary)
    y = np.arange(len(boundaries))
    h = 0.36

    fig, ax = plt.subplots(figsize=(3.45, 1.95))
    for k, c in enumerate(L.CORPORA):
        vals = d[f"{'github' if c.key == 'wildskills' else 'skillbench'}_pct"].astype(float)
        cnts = d[f"{'github' if c.key == 'wildskills' else 'skillbench'}_n"].astype(int)
        off = (k - 0.5) * h
        bars = ax.barh(y + off, vals, height=h, color=c.color,
                       label=c.label, zorder=3)
        for b, v, n in zip(bars, vals, cnts):
            ax.text(v + 0.7, b.get_y() + b.get_height() / 2,
                    f"{v:.1f}%  ({n})", va="center", ha="left", fontsize=6.4)

    ax.set_yticks(y)
    ax.set_yticklabels(boundaries)
    ax.invert_yaxis()
    ax.set_xlabel("Share of inconsistencies (%)")
    ax.set_xlim(0, float(d[["github_pct", "skillbench_pct"]].max().max()) * 1.42)
    ax.grid(axis="x", linewidth=0.35, alpha=0.35)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.01), handlelength=1.1,
              borderpad=0.2, ncol=2, columnspacing=1.4)
    L.save(fig, "fig3_artifact_boundary")


# --------------------------------------------------------------------------
def fig4_contract_facets() -> None:
    d = pd.read_csv(os.path.join(L.OUT, "fig4_facets.csv"))
    d = d.sort_values("both_pct", ascending=True)
    y = np.arange(len(d))
    h = 0.38

    fig, ax = plt.subplots(figsize=(3.45, 2.9))
    for k, c in enumerate(L.CORPORA):
        col = "github" if c.key == "wildskills" else "skillbench"
        off = (k - 0.5) * h
        bars = ax.barh(y + off, d[f"{col}_pct"].astype(float), height=h,
                       color=c.color, label=c.label, zorder=3)
        for b, v in zip(bars, d[f"{col}_pct"].astype(float)):
            ax.text(v + 0.35, b.get_y() + b.get_height() / 2, f"{v:.1f}",
                    va="center", ha="left", fontsize=6.0)

    ax.set_yticks(y)
    ax.set_yticklabels([L.FACET_DISPLAY[x] for x in d.facet], fontsize=7.4)
    ax.set_xlabel("Share of inconsistencies (%)")
    ax.set_xlim(0, float(d[["github_pct", "skillbench_pct"]].max().max()) * 1.22)
    ax.grid(axis="x", linewidth=0.35, alpha=0.35)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", handlelength=1.1, borderpad=0.2)
    L.save(fig, "fig4_contract_facets")


# --------------------------------------------------------------------------
def fig5_cooccurrence() -> None:
    f = pd.read_csv(os.path.join(L.OUT, "rq1_findings.csv"))
    order = L.BOUNDARY_ORDER
    mats = {}
    for c in L.CORPORA:
        sub = f[f.corpus == c.key]
        m = np.zeros((3, 3))
        for i, a in enumerate(order):
            sa = set(sub[sub.boundary == a].skill)
            if not sa:
                continue
            for j, b in enumerate(order):
                if i == j:
                    m[i, j] = np.nan
                    continue
                sb = set(sub[sub.boundary == b].skill)
                m[i, j] = len(sa & sb) / len(sa)
        mats[c.key] = m

    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.5), sharey=True,
                             gridspec_kw=dict(wspace=0.12))
    for ax, c in zip(axes, L.CORPORA):
        m = mats[c.key]
        im = ax.imshow(m, cmap="Blues", vmin=0, vmax=0.7)
        ax.set_xticks(range(3))
        ax.set_xticklabels(order, rotation=22, ha="right", fontsize=7)
        ax.set_yticks(range(3))
        ax.set_yticklabels(order, fontsize=7)
        ax.set_title(c.label, fontsize=8.5, pad=4)
        for i in range(3):
            for j in range(3):
                if i == j:
                    ax.text(j, i, "--", ha="center", va="center", fontsize=7,
                            color="0.55")
                else:
                    v = m[i, j]
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                            fontsize=7.4,
                            color="white" if v > 0.42 else "black")
        for s_ in ax.spines.values():
            s_.set_visible(False)
        ax.set_xticks(np.arange(-.5, 3, 1), minor=True)
        ax.set_yticks(np.arange(-.5, 3, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.8)
        ax.tick_params(which="minor", length=0)
    cb = fig.colorbar(im, ax=axes, fraction=0.03, pad=0.02)
    cb.set_label("P(boundary $j$ $\\mid$ boundary $i$)", fontsize=7.5)
    cb.ax.tick_params(labelsize=7)
    L.save(fig, "fig5_cooccurrence")


if __name__ == "__main__":
    fig2_count_distribution()
    fig3_artifact_boundary()
    fig4_contract_facets()
    fig5_cooccurrence()
