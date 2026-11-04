"""
Build the input package for the semantic re-verification of SkillBench findings.

For every finding we emit
  * the claimed taxonomy label,
  * the auditor's rationale and agent-impact note,
  * each evidence snippet together with the *actual* file content found on disk
    (resolved with path fallbacks, and located by content when the cited line
    numbers have drifted).

Output: outputs/verify_input.json
"""
from __future__ import annotations

import glob
import json
import os
import re

ROOT = "/workspace/skillEvaluation"
AUDIT = os.path.join(ROOT, "paper_audit_reports", "skillbench_audit")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
SKIP_DIRS = {".git", "node_modules", "__pycache__"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def resolve(skill_dir: str, rel: str) -> str | None:
    if not rel or str(rel).startswith("<"):
        return None
    rel = str(rel).strip().lstrip("/")
    parts = rel.split("/")
    cands = [os.path.join(skill_dir, rel)]
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
                return None
    return hits[0] if hits else None


def locate(lines: list[str], needle: str) -> int | None:
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
        if len(n) >= cut:
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


def window(path: str, lo: int | None, hi: int | None, pad: int = 6,
           limit: int = 2600) -> str:
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError:
        return ""
    if not lo:
        return "\n".join(lines[:40])[:limit]
    lo = max(1, lo - pad)
    hi = min(len(lines), (hi or lo) + pad)
    body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(lo, hi + 1))
    return body[:limit]


def main() -> None:
    items = []
    for rep in sorted(glob.glob(os.path.join(AUDIT, "*", "audit_report.json"))):
        skill = os.path.basename(os.path.dirname(rep))
        d = json.load(open(rep, encoding="utf-8"))
        skill_dir = d["meta"]["skill_dir"]
        for fd in d.get("findings", []):
            ev = fd.get("evidence") or {}
            ev_out = []
            for side in ("source_a", "source_b"):
                s = ev.get(side) or {}
                rel = s.get("file")
                if not rel:
                    continue
                ls, le = s.get("line_start"), s.get("line_end")
                quote = norm(s.get("span_text"))
                path = resolve(skill_dir, rel)
                found_at, actual = None, ""
                kind = "synthetic"
                if path:
                    lines = open(path, encoding="utf-8",
                                 errors="replace").read().split("\n")
                    at_range = norm("\n".join(lines[ls - 1:le])) if (
                        ls and le and 1 <= ls <= le <= len(lines)) else ""
                    if at_range and at_range == quote:
                        kind, found_at = "exact", ls
                    elif quote and quote in at_range:
                        kind, found_at = "in_range", ls
                    else:
                        found_at = locate(lines, quote)
                        kind = "drifted" if found_at else "not_found"
                    actual = window(path, found_at or ls, (found_at or ls) if found_at
                                    else le)
                ev_out.append({
                    "side": side,
                    "file": rel,
                    "resolved": os.path.relpath(path, skill_dir) if path else None,
                    "cited_lines": [ls, le],
                    "quote": quote[:900],
                    "match": kind,
                    "found_at_line": found_at,
                    "actual_content": actual,
                })
            items.append({
                "index": len(items),
                "key": f"{skill}|{fd.get('id')}",
                "skill": skill,
                "finding": fd.get("id"),
                "skill_dir": skill_dir,
                "claim": {
                    "l1": fd.get("taxonomy_l1"),
                    "l2": fd.get("taxonomy_l2"),
                    "l3": fd.get("taxonomy_l3"),
                },
                "severity": fd.get("severity"),
                "confidence": fd.get("confidence"),
                "checker": fd.get("source_checker"),
                "blocks_execution": bool((fd.get("agent_impact") or {})
                                         .get("blocks_execution")),
                "silent_error": bool((fd.get("agent_impact") or {})
                                     .get("produces_silent_error")),
                "impact": (fd.get("agent_impact") or {}).get("impact_description", ""),
                "rationale": fd.get("rationale", ""),
                "evidence": ev_out,
            })

    path = os.path.join(OUT, "verify_input.json")
    json.dump(items, open(path, "w"), ensure_ascii=False, indent=1)
    print(f"wrote {len(items)} findings -> {path}")
    from collections import Counter
    print("claim L1:", dict(Counter(i["claim"]["l1"] for i in items)))
    print("evidence match:", dict(Counter(e["match"] for i in items
                                          for e in i["evidence"])))


if __name__ == "__main__":
    main()
