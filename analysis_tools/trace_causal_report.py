#!/usr/bin/env python3
"""Trace-causal verdicts: did the skill actually cost effectiveness / efficiency?

Combines /tmp/trace_forensics.json (errors, recovery turns, finding matches) with a
finding-independent signal: any tool error whose text contains `/skills/`, i.e. the
skill's own code raised the exception in the agent's face.

Outputs skill_trace_causal_audit.csv and skill_trace_causal_audit.md.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re

RUNS_GLOB = (
    "hf_downloads/submissions/skillsbench/v1.1/"
    "claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/"
    "2026-01-29__paper-v1-xiangyi-completed-selected3/*__paper-v1-*"
)


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(text_of(x) for x in c)
    if isinstance(c, dict):
        return text_of(c.get("text") or c.get("content") or "")
    return ""


def skill_code_errors(log):
    """errors whose text references a path under /skills/ (skill's own code)"""
    out = []
    for line in open(log, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") != "user":
            continue
        for c in (o.get("message") or {}).get("content") or []:
            if not isinstance(c, dict) or c.get("type") != "tool_result":
                continue
            t = text_of(c.get("content"))
            if not (c.get("is_error") or "Traceback" in t[:400] or t.startswith("Exit code 1")):
                continue
            if "/skills/" in t:
                m = re.search(r"/skills/([A-Za-z0-9._+-]+)", t)
                first = next((ln for ln in t.splitlines()
                              if "Error" in ln or "error" in ln), t[:160])
                out.append(dict(skill=m.group(1) if m else "?",
                                line=first.strip()[:180]))
    return out


def main():
    forensics = {r["run"]: r for r in json.load(open("/tmp/trace_forensics.json"))}
    D = json.load(open("/tmp/impact_ranking.json"))
    rows = {r["task"]: r for r in D["rows"]}

    per_task = collections.defaultdict(list)
    for d in sorted(glob.glob(RUNS_GLOB)):
        task = os.path.basename(d).split("__")[0]
        log = os.path.join(d, "trajectory", "legacy_agent", "claude-code.txt")
        if not os.path.exists(log):
            continue
        run = os.path.basename(d)
        f = forensics.get(run)
        if not f:
            continue
        per_task[task].append(dict(
            run=run,
            reward=(json.load(open(os.path.join(d, "result.json"))).get("rewards") or {}).get("reward"),
            skill_code_errors=skill_code_errors(log),
            **{k: f[k] for k in ("turns", "out_tokens", "n_errors", "recovery_turns",
                                 "recovery_turn_share", "n_skill_loads", "skills_loaded",
                                 "agent_wrote_own_script", "skill_files_touched",
                                 "matched_strong_ids", "matched_medium_ids",
                                 "matched_evidence")},
        ))

    out = []
    for task, runs in per_task.items():
        n = len(runs)
        succ = sum(1 for r in runs if (r["reward"] or 0) >= 0.5) / n
        turns = sum(r["turns"] for r in runs)
        rec = sum(r["recovery_turns"] for r in runs)
        sc_runs = [r for r in runs if r["skill_code_errors"]]
        strong_runs = [r for r in runs if r["matched_strong_ids"]]
        med_runs = [r for r in runs if r["matched_medium_ids"]]
        bypass_runs = [r for r in runs if r["agent_wrote_own_script"]]
        matched = sorted({x for r in runs for x in r["matched_strong_ids"] + r["matched_medium_ids"]})

        if strong_runs and succ < 1.0:
            verdict = "effectiveness+efficiency 双降（STRONG）"
        elif strong_runs:
            verdict = "仅 efficiency 下降（STRONG）"
        elif med_runs and succ == 0.0:
            verdict = "effectiveness 下降（MEDIUM）"
        elif med_runs:
            verdict = "仅 efficiency 下降（MEDIUM）"
        elif sc_runs:
            verdict = "skill 代码报错但审计未覆盖"
        elif bypass_runs and len(bypass_runs) >= max(2, n - 1):
            verdict = "skill 被绕过，无因果机会"
        elif any(r["n_skill_loads"] for r in runs):
            verdict = "仅曝光，无因果证据"
        else:
            verdict = "skill 从未加载"

        r0 = rows.get(task, {})
        out.append(dict(
            task=task,
            rank=r0.get("rank"),
            iis=r0.get("IIS"),
            n_runs=n,
            success_rate=round(succ, 3),
            turns=turns,
            errors=sum(r["n_errors"] for r in runs),
            recovery_turns=rec,
            recovery_turn_share=round(rec / turns, 3) if turns else None,
            runs_with_skill_code_error=len(sc_runs),
            runs_with_strong_match=len(strong_runs),
            runs_with_medium_match=len(med_runs),
            runs_bypassing_skill=len(bypass_runs),
            matched_findings="|".join(matched),
            verdict=verdict,
            skill_error_samples=" || ".join(
                f"{e['skill']}: {e['line']}" for r in sc_runs for e in r["skill_code_errors"][:1])[:300],
        ))

    out.sort(key=lambda x: (x["rank"] is None, x["rank"] or 999))
    import csv
    with open("skill_trace_causal_audit.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        for r in out:
            w.writerow(r)

    json.dump(dict(tasks=out, runs=per_task), open("/tmp/trace_causal.json", "w"),
              ensure_ascii=False, indent=1, default=str)

    top = [r for r in out if r["rank"]]
    print(f"tasks={len(out)}  top30 classified={len(top)}")
    for r in top:
        print(f"{r['rank']:3} {r['task']:40} succ={r['success_rate']*100:3.0f}% "
              f"err={r['errors']:3} rec%={r['recovery_turn_share']*100 if r['recovery_turn_share'] else 0:3.0f} "
              f"scErr={r['runs_with_skill_code_error']} ST={r['runs_with_strong_match']} "
              f"MD={r['runs_with_medium_match']} bypass={r['runs_bypassing_skill']}  {r['verdict']}")


if __name__ == "__main__":
    main()
