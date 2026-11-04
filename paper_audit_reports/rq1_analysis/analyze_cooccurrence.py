"""
RQ1-C  Co-occurrence and heterogeneity (deliberately compact).

Answers
  * Do inconsistency types co-occur inside the same skill?
    -> P(T_j | T_i) at taxonomy level 1, per corpus and pooled
    -> strongest level-2 pairs
  * Are the patterns stable across skill domains?

Outputs
  outputs/table6_cooccurrence_l1.{csv,tex}
  outputs/table7_cooccurrence_pairs.{csv,tex}
  outputs/table8_domain_stability.{csv,tex}
  outputs/fig5_cooccurrence.csv

Run:  python3 analyze_cooccurrence.py
"""
from __future__ import annotations

import itertools
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rq1_lib as L  # noqa: E402


def presence(frame: pd.DataFrame, key: str, values: list[str]) -> pd.DataFrame:
    """skill x type boolean matrix."""
    tab = (frame.assign(one=1)
           .pivot_table(index=["corpus", "skill"], columns=key, values="one",
                        aggfunc="max", fill_value=0))
    for v in values:
        if v not in tab.columns:
            tab[v] = 0
    return tab[values].astype(bool)


def conditional(mat: pd.DataFrame, i: str, j: str) -> float:
    a = int(mat[i].sum())
    if not a:
        return float("nan")
    return int((mat[i] & mat[j]).sum()) / a


def main() -> None:
    f = pd.read_csv(os.path.join(L.OUT, "rq1_findings.csv"))
    s = pd.read_csv(os.path.join(L.OUT, "rq1_skills.csv"))

    # ---------------- level 1 ----------------
    mat_all = presence(f, "boundary", L.BOUNDARY_ORDER)
    mat_by = {c.key: presence(f[f.corpus == c.key], "boundary", L.BOUNDARY_ORDER)
              for c in L.CORPORA}

    rows = []
    for i, j in itertools.product(L.BOUNDARY_ORDER, repeat=2):
        row = [f"P({j} | {i})" if i != j else "---"]
        for c in L.CORPORA:
            v = conditional(mat_by[c.key], i, j)
            row.append("---" if i == j else f"{v:.2f}")
        v = conditional(mat_all, i, j)
        row.append("---" if i == j else f"{v:.2f}")
        rows.append(row)
    labels = [c.label for c in L.CORPORA]
    L.write_table(
        "table6_cooccurrence_l1",
        ["Condition"] + labels + ["Both"],
        rows,
        caption=("Conditional co-occurrence of artifact boundaries within the "
                 "same skill, P(boundary $j$ $\\mid$ boundary $i$). "
                 "Rows condition on skills that contain boundary $i$."),
        label="tab:rq1-cooccurrence-l1",
        align="l" + "r" * (len(labels) + 1),
        escape=False,
    )
    mat_all.astype(int).to_csv(os.path.join(L.OUT, "fig5_cooccurrence.csv"))

    # ---------------- level 2 pairs ----------------
    l2_types = (f.l2.value_counts().index.tolist())
    m2 = presence(f, "l2", l2_types)
    pair_rows = []
    for a, b in itertools.combinations(l2_types, 2):
        both = int((m2[a] & m2[b]).sum())
        if both < 8:
            continue
        p_b_a = conditional(m2, a, b)
        p_a_b = conditional(m2, b, a)
        pair_rows.append([a, b, both, f"{p_b_a:.2f}", f"{p_a_b:.2f}",
                          f"{p_b_a + p_a_b:.2f}"])
    pair_rows.sort(key=lambda r: -float(r[5]))

    def tt(name: str) -> str:
        """monospace, underscore-safe L2 name for the (unescaped) LaTeX table"""
        return name.replace("_", r"\_")

    pair_rows = [[tt(r[0]), tt(r[1])] + r[2:] for r in pair_rows]
    L.write_table(
        "table7_cooccurrence_pairs",
        ["Type $i$", "Type $j$", "Skills with both",
         "P($j$ $\\mid$ $i$)", "P($i$ $\\mid$ $j$)"],
        [r[:5] for r in pair_rows[:10]],
        caption=("Strongest level-2 type pairs co-occurring within the same "
                 "skill (both corpora pooled); pairs that co-occur in fewer "
                 "than 8 skills are omitted."),
        label="tab:rq1-cooccurrence-pairs",
        align="llrrr",
        size=r"\footnotesize",
        escape=False,
    )

    # ---------------- multi-boundary skills ----------------
    n_bound = mat_all.sum(axis=1)
    multi = int((n_bound >= 2).sum())
    with_find = int((n_bound >= 1).sum())
    multi_rows = [["Skills with at least one inconsistency", with_find, "100.0\\%"],
                  ["...spanning $\\geq$ 2 artifact boundaries", multi,
                   f"{100 * multi / with_find:.1f}\\%"],
                  ["...spanning all 3 artifact boundaries",
                   int((n_bound == 3).sum()),
                   f"{100 * (n_bound == 3).sum() / with_find:.1f}\\%"]]
    L.write_table(
        "table6b_multiboundary",
        ["Group", "Skills", "Share"],
        multi_rows,
        caption=("How many artifact boundaries a single skill violates at once."),
        label="tab:rq1-multiboundary",
        align="lrr",
        escape=False,
    )

    # ---------------- domain stability ----------------
    dom = s[(s.domain.notna()) & (s.domain != "")][["corpus", "skill", "domain"]]
    fb = f.merge(dom, on=["corpus", "skill"], how="inner")
    rows = []
    for domain, sub in fb.groupby("domain"):
        skills = dom[dom.domain == domain]
        n_skills = len(skills)
        if n_skills < 20:
            continue
        n = len(sub)
        row = [domain, n_skills, n]
        for b in L.BOUNDARY_ORDER:
            nb = int((sub.boundary == b).sum())
            row.append(f"{100 * nb / n:.1f}\\%")
        # share of this domain's skills that span >= 2 boundaries
        mm = presence(sub, "boundary", L.BOUNDARY_ORDER)
        row.append(f"{100 * (mm.sum(axis=1) >= 2).mean():.1f}\\%")
        rows.append(row)
    rows.sort(key=lambda r: -r[1])
    L.write_table(
        "table8_domain_stability",
        ["Domain", "Skills", "Findings"] + [f"{L.BOUNDARY_SHORT[b]} (\\%)" for b in L.BOUNDARY_ORDER]
        + ["$\\geq$2 boundaries (\\%)"],
        rows,
        caption=("Artifact-boundary mix by skill domain (domains with at least "
                 "20 audited skills). Skill--Env. = Skill--Environment, "
                 "Doc--Code = Document--Code, Doc--Doc = Document--Document. "
                 "The last column is the share of the domain's skills whose "
                 "findings span two or more boundaries."),
        label="tab:rq1-domain",
        align="l" + "r" * (len(rows[0]) - 1),
        size=r"\footnotesize",
        escape=False,
        resize=True,
    )

    # ---------------- console ----------------
    print(f"\nskills with >=1 finding: {with_find}; spanning >=2 boundaries: "
          f"{multi} ({100 * multi / with_find:.1f}%)")
    print("\nP(j|i) at boundary level (pooled):")
    for i in L.BOUNDARY_ORDER:
        print("  ", i, {j: round(conditional(mat_all, i, j), 2)
                        for j in L.BOUNDARY_ORDER if j != i})
    print("\ntop L2 pairs:")
    for r in pair_rows[:6]:
        print("  ", r)


if __name__ == "__main__":
    main()
