"""
SkillBench evidence-integrity check.

For every evidence snippet in the 87 SkillBench audit reports, locate the cited
file on disk and decide whether the quoted text really is there:

    exact             quoted lines == cited line range
    in_range          quoted text appears inside the cited line range
    range_in_span     cited range is a subset of the quoted text
    drifted           text exists in the file but at other lines (line drift)
    not_found         text cannot be located in that file
    placeholder       the report used a synthetic file name (e.g. '<code literal>')
    file_missing      file cannot be resolved on disk

Output: outputs/evidence_integrity.csv  (+ console summary)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
from collections import Counter

ROOT = "/workspace/skillEvaluation"
AUDIT = os.path.join(ROOT, "paper_audit_reports", "skillbench_audit")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUT, exist_ok=True)

SKIP_DIRS = {".git", "node_modules", "__pycache__"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def resolve(skill_dir: str, rel: str) -> str | None:
    """Resolve a report-relative path, tolerating spurious prefixes."""
    if not rel or rel.startswith("<"):
        return None
    rel = rel.strip().lstrip("/")
    cands = [os.path.join(skill_dir, rel)]
    parts = rel.split("/")
    for i in range(1, min(4, len(parts))):
        cands.append(os.path.join(skill_dir, "/".join(parts[i:])))
    for c in cands:
        if os.path.isfile(c):
            return c
    base = os.path.basename(rel)
    hits = []
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if base in files:
            hits.append(os.path.join(root, base))
            if len(hits) > 1:
                break
    return hits[0] if len(hits) == 1 else None


def locate(lines: list[str], needle: str) -> int | None:
    """Return the 1-based line where `needle` starts, or None."""
    n = norm(needle)
    if len(n) < 20:
        return None
    blob, idx = [], []
    for i, ln in enumerate(lines):
        t = norm(ln)
        if t:
            blob.append(t)
            idx.append(i + 1)
    joined = " ".join(blob)
    pos = -1
    for cut in (120, 90, 60, 40):
        pos = joined.find(n[:cut])
        if pos >= 0:
            break
    if pos < 0:
        return None
    acc = 0
    for t, ln in zip(blob, idx):
        if acc + len(t) >= pos:
            return ln
        acc += len(t) + 1
    return idx[-1] if idx else None


def main() -> None:
    rows = []
    for rep in sorted(glob.glob(os.path.join(AUDIT, "*", "audit_report.json"))):
        skill = os.path.basename(os.path.dirname(rep))
        d = json.load(open(rep, encoding="utf-8"))
        skill_dir = d["meta"]["skill_dir"]
        for fd in d.get("findings", []):
            ev = fd.get("evidence") or {}
            for side in ("source_a", "source_b"):
                s = ev.get(side) or {}
                rel = s.get("file")
                if not rel:
                    continue
                ls, le = s.get("line_start"), s.get("line_end")
                span = norm(s.get("span_text"))
                rec = dict(skill=skill, finding=fd.get("id"), side=side,
                           checker=fd.get("source_checker"), l1=fd.get("taxonomy_l1"),
                           l2=fd.get("taxonomy_l2"), l3=fd.get("taxonomy_l3"),
                           file=rel, line_start=ls, line_end=le,
                           status="", found_at="", drift="")
                if str(rel).startswith("<"):
                    rec["status"] = "placeholder"
                    rows.append(rec)
                    continue
                path = resolve(skill_dir, rel)
                if not path:
                    rec["status"] = "file_missing"
                    rows.append(rec)
                    continue
                rec["resolved"] = os.path.relpath(path, skill_dir)
                lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
                actual = norm("\n".join(lines[ls - 1:le])) if (
                    ls and le and 1 <= ls <= le <= len(lines)) else ""
                if actual and actual == span:
                    rec["status"] = "exact"
                elif span and span in actual:
                    rec["status"] = "in_range"
                elif actual and actual in span:
                    rec["status"] = "range_in_span"
                else:
                    at = locate(lines, span)
                    if at is None:
                        rec["status"] = "not_found"
                    else:
                        rec["status"] = "drifted"
                        rec["found_at"] = at
                        if ls:
                            rec["drift"] = at - ls
                rows.append(rec)

    with open(os.path.join(OUT, "evidence_integrity.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    c = Counter(r["status"] for r in rows)
    print(f"snippets checked: {len(rows)}")
    for k, v in c.most_common():
        print(f"  {k:14s} {v:4d}  ({100 * v / len(rows):.1f}%)")

    # roll up to findings: a finding is clean only if all its snippets are exact
    clean, flagged = set(), {}
    for r in rows:
        key = (r["skill"], r["finding"])
        if r["status"] == "exact":
            clean.add(key)
        else:
            flagged.setdefault(key, []).append(r["status"])
    all_keys = {(r["skill"], r["finding"]) for r in rows}
    print(f"\nfindings with all snippets exact : {len(clean)}/{len(all_keys)}")
    print(f"findings with >=1 flagged snippet: {len(flagged)}/{len(all_keys)}")
    worst = Counter()
    for k, v in flagged.items():
        for s in v:
            worst[s] += 1
    print("  flagged snippet types:", dict(worst))

    nf = {(r["skill"], r["finding"]) for r in rows if r["status"] == "not_found"}
    print(f"\nfindings with an unlocatable quote: {len(nf)}")
    for s, f in sorted(nf):
        print(f"   {s} {f}")


if __name__ == "__main__":
    main()
