"""
RQ1 shared library: corpus definitions, taxonomy normalisation, contract-claim
counting and the plotting style used by every RQ1 script.

Everything in RQ1 is derived from the audited reports under
    paper_audit_reports/skillbench_audit/*/audit_report.json   (SkillBench)
    paper_audit_reports/wildskills_audit/*/audit_report.json   (GitHub skills)

Run `build_dataset.py` first: it writes outputs/rq1_findings.csv and
outputs/rq1_skills.csv, which all downstream scripts consume.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAPER = os.path.join(ROOT, "paper_audit_reports")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
FIG = os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)
os.makedirs(FIG, exist_ok=True)

# domain labels produced by paper_audit_reports/skill_category_distribution.csv
DOMAIN_CSV = os.path.join(PAPER, "skill_category_distribution.csv")


# --------------------------------------------------------------------------
# corpora
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Corpus:
    key: str          # internal id, also the value in the `corpus` column
    label: str        # label used in figures / tables
    short: str        # compact label
    audit_dir: str
    color: str


CORPORA = [
    Corpus("wildskills", "GitHub Skills", "GitHub",
           os.path.join(PAPER, "wildskills_audit"), "#4C72B0"),
    Corpus("skillbench", "SkillBench", "SkillBench",
           os.path.join(PAPER, "skillbench_audit"), "#DD8452"),
]
CORPUS_BY_KEY = {c.key: c for c in CORPORA}
# left-to-right order used everywhere (GitHub first: it is the larger corpus)
ORDER = ["wildskills", "skillbench"]


# --------------------------------------------------------------------------
# taxonomy
# --------------------------------------------------------------------------
# taxonomy_l1 -> artifact boundary at which the contract breaks
BOUNDARY = {
    "environmental": "Skill\u2013Environment",
    "implementation": "Document\u2013Code",
    "document": "Document\u2013Document",
}
BOUNDARY_ORDER = ["Skill\u2013Environment", "Document\u2013Code", "Document\u2013Document"]
# compact labels for narrow tables (defined in the captions)
BOUNDARY_SHORT = {
    "Skill\u2013Environment": "Skill--Env.",
    "Document\u2013Code": "Doc--Code",
    "Document\u2013Document": "Doc--Doc",
}
BOUNDARY_COLOR = {
    "Skill\u2013Environment": "#B4C7E7",
    "Document\u2013Code": "#4C72B0",
    "Document\u2013Document": "#8FAADC",
}

# the audit pipeline emitted two spellings for the same L2 type
L2_ALIAS = {
    "semantically_conflicting": "semantic_conflict",
    "over-promised": "over_promised",
    "under-promised": "under_promised",
    "environmental": "environmental",
}
L2_DISPLAY = {
    "environment_fact_conflict": "environment_fact_conflict",
    "over_promised": "over_promised",
    "shared_concept_definition_conflict": "shared_concept_definition_conflict",
    "cross_document_process_conflict": "cross_document_process_conflict",
    "semantic_conflict": "semantic_conflict",
    "interface_contract_mismatch": "interface_contract_mismatch",
    "external_resource_invalid": "external_resource_invalid",
    "external_service_contract_change": "external_service_contract_change",
    "dependency_version_drift": "dependency_version_drift",
    "under_promised": "under_promised",
}

# (l2, l3) -> the part of the skill contract that is violated.
# L3 exists only for the implementation layer; for the document/environmental
# layers the L2 type already names the contract element.
FACET_MAP = {
    # Document-Code (implementation)
    ("over_promised", "missing_parameter"): "parameter",
    ("semantic_conflict", "semantic_param_conflict"): "parameter",
    ("under_promised", "implicit_param_support"): "parameter",
    ("over_promised", "missing_return_field"): "return",
    ("semantic_conflict", "semantic_return_conflict"): "return",
    ("under_promised", "implicit_return_info"): "return",
    ("over_promised", "unimplemented_feature"): "capability",
    ("under_promised", "implicit_feature_extension"): "capability",
    ("over_promised", "missing_constraint_or_exception"): "constraint",
    ("under_promised", "implicit_fault_tolerance"): "fault_tolerance",
    ("semantic_conflict", "workflow_conflict"): "workflow",
    ("semantic_conflict", "side_effect_conflict"): "side_effect",
    # Document-Document
    ("interface_contract_mismatch", None): "interface",
    ("shared_concept_definition_conflict", None): "concept",
    ("cross_document_process_conflict", None): "workflow",
    # Skill-Environment
    ("external_resource_invalid", None): "resource",
    ("dependency_version_drift", None): "dependency",
    ("external_service_contract_change", None): "service_contract",
    ("environment_fact_conflict", None): "environment",
}
# fallbacks when an implementation finding carries no L3
FACET_FALLBACK = {
    "over_promised": "capability",
    "semantic_conflict": "semantic",
    "under_promised": "capability",
}
FACET_ORDER = [
    "environment", "capability", "concept", "interface", "workflow",
    "parameter", "return", "constraint", "side_effect", "resource",
    "dependency", "service_contract", "fault_tolerance", "semantic",
]
FACET_DISPLAY = {
    "environment": "environment assumption",
    "capability": "capability",
    "concept": "shared concept",
    "interface": "interface / schema",
    "workflow": "workflow",
    "parameter": "parameter",
    "return": "return value",
    "constraint": "constraint / exception",
    "side_effect": "side effect",
    "resource": "external resource",
    "dependency": "dependency version",
    "service_contract": "external service contract",
    "fault_tolerance": "fault tolerance",
    "semantic": "semantic (unclassified)",
}


def normalise_l2(l1: str | None, l2: str | None) -> str:
    l2 = (l2 or "unknown").strip()
    return L2_ALIAS.get(l2, l2)


def boundary_of(l1: str | None) -> str:
    return BOUNDARY.get((l1 or "").strip(), "Other")


def facet_of(l1: str | None, l2: str | None, l3: str | None) -> str:
    l2n = normalise_l2(l1, l2)
    l3n = (l3 or "").strip() or None
    if (l2n, l3n) in FACET_MAP:
        return FACET_MAP[(l2n, l3n)]
    if (l2n, None) in FACET_MAP:
        return FACET_MAP[(l2n, None)]
    if l2n in FACET_FALLBACK:
        return FACET_FALLBACK[l2n]
    return "other"


# --------------------------------------------------------------------------
# resolving the audited skill directory on this machine
# --------------------------------------------------------------------------
def resolve_skill_dir(name: str, meta_dir: str | None) -> str | None:
    """Audit reports were produced on a cluster, so meta.skill_dir is often a
    remote path. Fall back to the local mirrors."""
    for cand in (meta_dir,
                 os.path.join(ROOT, "wildskills", "skills", name),
                 os.path.join(ROOT, "wildskills", "scripts_skills", name)):
        if cand and os.path.isdir(cand):
            return cand
    return None


# --------------------------------------------------------------------------
# contract-claim counting (density denominator)
# --------------------------------------------------------------------------
DOC_EXT = {".md", ".mdx", ".markdown", ".rst", ".txt", ".org"}
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".java", ".kt",
            ".go", ".rs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cs",
            ".rb", ".php", ".sh", ".bash", ".zsh", ".sql", ".swift", ".scala",
            ".lua", ".pl", ".r", ".m", ".mm", ".vue", ".svelte"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".next", "target", "vendor", ".mypy_cache", ".pytest_cache"}

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)

_CODE_PATTERNS = [
    # python
    re.compile(r"^\s*(?:async\s+)?def\s+\w+\s*\((?P<args>[^)]*)\)", re.M),
    # js / ts function declarations, methods and arrow assignments
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+\s*\((?P<args>[^)]*)\)", re.M),
    re.compile(r"^\s*(?:public|private|protected|static|async|final|\s)*\w[\w<>\[\],\s]*\s+\w+\s*\((?P<args>[^)]*)\)\s*\{", re.M),
    re.compile(r"^(?:export\s+)?const\s+\w+\s*=\s*(?:async\s*)?\((?P<args>[^)]*)\)\s*=>", re.M),
    # go
    re.compile(r"^func\s+(?:\([^)]*\)\s*)?\w+\s*\((?P<args>[^)]*)\)", re.M),
    # rust
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+\w+\s*\((?P<args>[^)]*)\)", re.M),
]


def _sentence_count(text: str) -> int:
    parts = re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", text)
    n = 0
    for p in parts:
        p = p.strip()
        if len(p) < 8:
            continue
        words = len(re.findall(r"[A-Za-z0-9_\-]+", p))
        cjk = len(re.findall(r"[\u4e00-\u9fff]", p))
        if words >= 3 or cjk >= 6:
            n += 1
    return n


def count_doc_claims(path: str) -> tuple[int, int]:
    """Return (claims, lines) for one documentation file.

    A claim is a sentence, a list item or a table row that states something
    about the skill's behaviour. Headings, fences, rules and frontmatter are
    not claims.
    """
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return 0, 0
    text = _FRONTMATTER.sub("", text)
    lines = text.splitlines()
    claims = 0
    in_fence = False
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, claims
        if buffer:
            claims += _sentence_count(" ".join(buffer))
            buffer = []

    for raw in lines:
        if _FENCE.match(raw):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = raw.rstrip()
        if not line.strip() or _HEADING.match(line) or _RULE.match(line):
            flush()
            continue
        if _TABLE_ROW.match(line):
            flush()
            if not _TABLE_SEP.match(line):
                claims += 1
            continue
        if _LIST_ITEM.match(line):
            flush()
            body = _LIST_ITEM.sub("", line).strip()
            claims += max(1, _sentence_count(body)) if body else 0
            continue
        buffer.append(line.strip())
    flush()
    return claims, len(lines)


def count_code_claims(path: str) -> tuple[int, int]:
    """Return (interface claims, non-blank LOC) for one source file.

    Interface claims = number of callable definitions + number of declared
    parameters across those definitions.
    """
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return 0, 0
    loc = sum(1 for ln in text.splitlines() if ln.strip())
    defs = 0
    params = 0
    for pat in _CODE_PATTERNS:
        for m in pat.finditer(text):
            args = (m.group("args") or "").strip()
            defs += 1
            if args:
                depth = 0
                n = 1
                for ch in args:
                    if ch in "([{<":
                        depth += 1
                    elif ch in ")]}>":
                        depth -= 1
                    elif ch == "," and depth == 0:
                        n += 1
                params += n
    return defs + params, loc


def measure_skill(skill_dir: str) -> dict:
    """Contract-surface measurements for one skill directory."""
    doc_claims = doc_lines = code_claims = code_loc = 0
    n_doc = n_code = n_files = 0
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            p = os.path.join(root, fn)
            ext = os.path.splitext(fn)[1].lower()
            n_files += 1
            if ext in DOC_EXT:
                c, l = count_doc_claims(p)
                doc_claims += c
                doc_lines += l
                n_doc += 1
            elif ext in CODE_EXT:
                c, l = count_code_claims(p)
                code_claims += c
                code_loc += l
                n_code += 1
    return {
        "contract_claims": doc_claims + code_claims,
        "doc_claims": doc_claims,
        "code_claims": code_claims,
        "code_loc": code_loc,
        "doc_lines": doc_lines,
        "n_files": n_files,
        "n_doc_files": n_doc,
        "n_code_files": n_code,
    }


# --------------------------------------------------------------------------
# plotting style
# --------------------------------------------------------------------------
def apply_style() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Nimbus Roman", "Liberation Serif",
                       "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "axes.linewidth": 0.7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "xtick.major.size": 2.6,
        "ytick.major.size": 2.6,
        "legend.frameon": False,
        "figure.dpi": 200,
        "savefig.dpi": 400,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def save(fig, stem: str) -> None:
    """Save a figure as vector PDF (for LaTeX) and PNG (for previewing)."""
    import matplotlib.pyplot as plt
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(FIG, f"{stem}.{ext}"))
    plt.close(fig)
    print(f"  figure -> figures/{stem}.pdf / .png")


def fmt_pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f}\\%"


# --------------------------------------------------------------------------
# table output (CSV for analysis + LaTeX for the paper)
# --------------------------------------------------------------------------
_TEX_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def tex_escape(s) -> str:
    s = str(s)
    return "".join(_TEX_SPECIAL.get(ch, ch) for ch in s)


def write_table(stem: str, header: list[str], rows: list[list], *,
                caption: str = "", label: str = "", note: str = "",
                align: str | None = None, size: str = r"\small",
                bold_rows: set[int] | None = None,
                escape: bool = True, raw_header: bool = False,
                resize: bool = False) -> None:
    """Write outputs/<stem>.csv and outputs/<stem>.tex (booktabs)."""
    import csv as _csv
    with open(os.path.join(OUT, f"{stem}.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)

    align = align or ("l" + "r" * (len(header) - 1))
    bold_rows = bold_rows or set()
    esc = tex_escape if escape else (lambda s: str(s))
    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{%s}" % caption,
        r"  \label{%s}" % label,
        "  %s" % size,
        r"  \setlength{\tabcolsep}{4pt}",
        (r"  \resizebox{\ifdim\width>\linewidth \linewidth\else\width\fi}{!}{%"
         if resize else ""),
        r"  \begin{tabular}{%s}" % align,
        r"    \toprule",
        "    " + " & ".join((str(h) if raw_header else esc(h))
                            for h in header) + r" \\",
        r"    \midrule",
    ]
    for i, row in enumerate(rows):
        cells = " & ".join(esc(c) for c in row)
        if i in bold_rows:
            cells = r"\textbf{%s}" % cells
        lines.append("    " + cells + r" \\")
    lines += [r"    \bottomrule", r"  \end{tabular}"]
    if resize:
        lines.append(r"  }%")
    if note:
        lines += [
            r"  \\[2pt]",
            r"  \begin{minipage}{\linewidth}",
            r"    \footnotesize\raggedright " + note,
            r"  \end{minipage}",
        ]
    lines += [r"\end{table}", ""]
    open(os.path.join(OUT, f"{stem}.tex"), "w", encoding="utf-8").write(
        "\n".join(lines))
    print(f"  table  -> outputs/{stem}.csv / .tex")


def pct(n: float, d: float, nd: int = 1) -> str:
    return "n/a" if not d else f"{100 * n / d:.{nd}f}"
