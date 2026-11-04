#!/usr/bin/env python3
"""Trace-level causal audit of the paper-v1 with-skills runs.

For every run of every audited task, reconstruct the agent's ordered action stream
and answer four questions:

  1. Was the skill loaded, and at which turn?          -> doc exposure
  2. Were the skill's own files/scripts used?          -> file exposure / adoption
  3. Did the run hit errors, and do those errors name  -> causal link candidate
     a symbol that appears in one of the audit findings?
  4. How much of the run was spent in error->fix       -> efficiency cost
     cycles, and did the task end up completing?

Outputs /tmp/trace_forensics.json and trace_forensics.csv (top-30 tasks flagged).
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import statistics
from collections import Counter, defaultdict

RUNS_GLOB = (
    "hf_downloads/submissions/skillsbench/v1.1/"
    "claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/"
    "2026-01-29__paper-v1-xiangyi-completed-selected3/*__paper-v1-*"
)
TOP30 = json.load(open("/tmp/impact_ranking.json"))["top30"] if os.path.exists("/tmp/impact_ranking.json") else []

ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{4,}")
# identifiers that are too common to be evidence of a causal link, observed as
# false positives when matching tracebacks against finding evidence
GENERIC = set("""
python command directory analysis query apache operation frames frame scale shape
columns column append start policy downtime baseline solution goals goal lists list
problem domain object output input value error path file data result results
machine job jobs task tasks time index name names type types number count
suricata check run script code line test tests api request response
""".split())
# short package/tool names that ARE diagnostic even though they carry no
# underscore, dot or internal capital
SPECIFIC_EXTRA = {"markitdown", "atheris", "wyckoff", "pymatgen", "openpyxl",
                  "opencv", "ffmpeg", "suricata", "pandas", "numpy", "scipy"}


def is_specific(tok):
    if tok.lower() in GENERIC:
        return False
    if tok.lower() in SPECIFIC_EXTRA:
        return True
    if len(tok) < 6:
        return False
    return ("_" in tok) or any(c.isupper() for c in tok[1:])

ERROR_MARKERS = (
    "Traceback (most recent call last)", "Error:", "error:", "ERROR",
    "ModuleNotFoundError", "ImportError", "NameError", "AttributeError",
    "FileNotFoundError", "TypeError", "ValueError", "KeyError", "IndexError",
    "AssertionError", "SyntaxError", "CalledProcessError", "connect_error",
    "HTTP 4", "HTTP 5", "404", "500", "FAILED", "failing", "No such file",
    "command not found", "not found", "unrecognized arguments",
)
# identifiers that carry no diagnostic value when matching errors to findings
STOP = set("""
the and for with from that this these those when then than which where while
should would could must have has had been being does does not but all any
agent skill skills file files code line lines data task tasks test tests
value values name names type types list dict str int float bool none true false
true false print return import from class def self error errors found using
""".split())


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text_of(c) for c in content)
    if isinstance(content, dict):
        return text_of(content.get("text") or content.get("content") or "")
    return ""


def is_error_result(txt, flag):
    if flag:
        return True
    head = txt[:600]
    if "Traceback (most recent call last)" in head:
        return True
    if re.search(r"^Exit code [1-9]", head.strip()):
        return True
    if "<tool_use_error>" in head:
        return True
    return False


def find_identifiers(*texts):
    out = set()
    for t in texts:
        for m in ID_RE.finditer(t or ""):
            tok = m.group(0)
            if tok.lower() in STOP or len(tok) < 5:
                continue
            out.add(tok)
    return out


def load_finding_keywords(task, reports_cache):
    """finding id -> set of identifiers that would appear in an error caused by it"""
    rep = reports_cache.get(task)
    if rep is None:
        p = f"tasks/{task}/audit_report.json"
        rep = json.load(open(p)) if os.path.exists(p) else {}
        reports_cache[task] = rep
    out = {}
    for f in rep.get("findings") or []:
        ev = f.get("evidence") or {}
        span_ids, files = set(), []
        for k in ("source_a", "source_b"):
            span = (ev.get(k) or {}).get("span_text") or ""
            fp = (ev.get(k) or {}).get("file") or ""
            span_ids |= find_identifiers(span)
            if fp and not fp.startswith("<"):
                files.append(fp)
        rationale_ids = find_identifiers(f.get("rationale") or "",
                                        (f.get("agent_impact") or {}).get("impact_description") or "")
        out[f.get("id")] = dict(
            span_ids=span_ids,           # identifiers that literally appear in the evidence
            rationale_ids=rationale_ids,  # weaker: only mentioned in prose
            severity=f.get("severity"),
            impact=(f.get("agent_impact") or {}).get("impact_class"),
            confidence=f.get("confidence"),
            files=files,
            skill_dirs=sorted({x.split("/")[0] for x in files}),
        )
    return out


def scan_run(log_path, finding_kw):
    """Reconstruct the ordered event stream and derive forensic measures."""
    events = []           # (kind, payload)
    turn = 0
    total_out_tokens = 0
    turns_with_err = set()
    errors = []           # dicts
    skill_loads = []      # dicts
    writes = []           # agent-authored files
    reads = []            # file paths read
    bash_cmds = []

    with open(log_path, errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            if t == "assistant":
                msg = o.get("message") or {}
                u = msg.get("usage") or {}
                total_out_tokens += u.get("output_tokens") or 0
                for c in msg.get("content") or []:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use":
                        turn += 1
                        nm = c.get("name")
                        inp = c.get("input") or {}
                        if nm == "Skill":
                            skill_loads.append(dict(turn=turn, skill=inp.get("skill"),
                                                    args=str(inp.get("args") or "")[:200]))
                        elif nm == "Read":
                            reads.append(dict(turn=turn, path=inp.get("file_path") or ""))
                        elif nm == "Write":
                            writes.append(dict(turn=turn, path=inp.get("file_path") or ""))
                        elif nm == "Bash":
                            bash_cmds.append(dict(turn=turn, cmd=(inp.get("command") or "")[:400]))
                        events.append((turn, nm, inp))
            elif t == "user":
                for c in (o.get("message") or {}).get("content") or []:
                    if not isinstance(c, dict) or c.get("type") != "tool_result":
                        continue
                    txt = text_of(c.get("content"))
                    if is_error_result(txt, bool(c.get("is_error"))):
                        turns_with_err.add(turn)
                        errors.append(dict(turn=turn, text=txt[:1500]))

    # ---- error -> finding matching (tiered) ----------------------------- #
    err_ids = [find_identifiers(e["text"]) for e in errors]
    matched_findings = Counter()
    matched_evidence = []
    for e, ids in zip(errors, err_ids):
        for fid, meta in finding_kw.items():
            # tier 1 (STRONG): the traceback runs through the skill's own file
            strong = any(f"/skills/{d}/" in e["text"] for d in meta["skill_dirs"])
            # tier 2 (MEDIUM): the error names a *specific* symbol that appears
            # verbatim in the finding's code/doc evidence
            hits = {x for x in (ids & meta["span_ids"]) if is_specific(x)}
            medium = bool(hits)
            if not (strong or medium):
                continue
            matched_findings[fid] += 1
            matched_evidence.append(dict(
                turn=e["turn"],
                finding=fid,
                tier="STRONG" if strong else "MEDIUM",
                matched=sorted(hits)[:6],
                severity=meta["severity"],
                impact=meta["impact"],
                file=(meta["files"][0] if meta["files"] else None),
                err=(e["text"][:220]),
            ))
    matched_evidence.sort(key=lambda x: (x["tier"] != "STRONG", x["turn"]))

    # ---- error signature repetition (thrashing) ------------------------- #
    sig = Counter()
    for e in errors:
        first = next((ln for ln in e["text"].splitlines()
                      if any(m in ln for m in ERROR_MARKERS)), e["text"][:80])
        sig[re.sub(r"\d+", "#", first.strip())[:120]] += 1
    repeats = sum(v - 1 for v in sig.values() if v > 1)

    first_load = skill_loads[0]["turn"] if skill_loads else None
    err_after_load = sum(1 for e in errors if first_load and e["turn"] >= first_load)
    err_before_load = len(errors) - err_after_load
    skill_files_touched = sum(1 for b in bash_cmds if "/skills/" in b["cmd"]) + \
                          sum(1 for r in reads if "/skills/" in (r["path"] or ""))

    # ---- recovery cost: turns burned between an error and the next good result
    err_turns = sorted({e["turn"] for e in errors})
    good_turns = sorted({t for t, _, _ in events} - set(err_turns))
    recovery_turns = 0
    for et in err_turns:
        nxt = next((g for g in good_turns if g > et), None)
        if nxt is not None:
            recovery_turns += nxt - et
    strong_ids = sorted({m["finding"] for m in matched_evidence if m["tier"] == "STRONG"})
    medium_ids = sorted({m["finding"] for m in matched_evidence if m["tier"] == "MEDIUM"})

    return dict(
        turns=turn,
        out_tokens=total_out_tokens,
        n_errors=len(errors),
        n_turns_with_error=len(turns_with_err),
        error_rate=round(len(turns_with_err) / turn, 3) if turn else None,
        recovery_turns=recovery_turns,
        recovery_turn_share=round(recovery_turns / turn, 3) if turn else None,
        err_before_first_skill_load=err_before_load,
        err_after_first_skill_load=err_after_load,
        repeated_error_signatures=repeats,
        distinct_error_signatures=len(sig),
        skill_loads=skill_loads,
        first_skill_load_turn=first_load,
        n_skill_loads=len(skill_loads),
        skills_loaded=sorted({s["skill"] for s in skill_loads if s["skill"]}),
        n_agent_writes=len(writes),
        agent_wrote_own_script=any(
            (w["path"] or "").endswith((".py", ".js", ".mjs", ".sh")) and "/skills/" not in (w["path"] or "")
            for w in writes),
        skill_files_touched=skill_files_touched,
        matched_strong_ids=strong_ids,
        matched_medium_ids=medium_ids,
        matched_finding_ids=sorted(set(strong_ids) | set(medium_ids)),
        matched_finding_error_count=sum(matched_findings.values()),
        matched_evidence=matched_evidence[:12],
        error_signatures=dict(sig.most_common(6)),
    )


def main():
    reports_cache = {}
    rows = []
    for d in sorted(glob.glob(RUNS_GLOB)):
        task = os.path.basename(d).split("__")[0]
        log = os.path.join(d, "trajectory", "legacy_agent", "claude-code.txt")
        if not os.path.exists(log):
            continue
        try:
            res = json.load(open(os.path.join(d, "result.json")))
        except Exception:
            continue
        kw = load_finding_keywords(task, reports_cache)
        forged = scan_run(log, kw)
        rows.append(dict(
            task=task,
            run=os.path.basename(d),
            top30=task in TOP30,
            reward=(res.get("rewards") or {}).get("reward"),
            t_total=(res.get("timing") or {}).get("total"),
            t_agent=(res.get("timing") or {}).get("agent_execution"),
            **forged,
        ))

    json.dump(rows, open("/tmp/trace_forensics.json", "w"), ensure_ascii=False, indent=1)

    cols = [k for k in rows[0] if k not in ("skill_loads", "matched_evidence",
                                            "error_signatures", "skills_loaded")]
    with open("trace_forensics.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"runs scanned: {len(rows)}  tasks: {len({r['task'] for r in rows})}")
    n_match = sum(1 for r in rows if r["matched_finding_ids"])
    print(f"runs with >=1 error textually matching an audit finding: {n_match}")
    print(f"runs with a skill loaded: {sum(1 for r in rows if r['n_skill_loads'])}")
    print(f"runs that wrote their own script: {sum(1 for r in rows if r['agent_wrote_own_script'])}")
    tot_err = sum(r["n_errors"] for r in rows)
    print(f"total tool errors: {tot_err}; total turns: {sum(r['turns'] for r in rows)}")


if __name__ == "__main__":
    main()
