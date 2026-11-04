"""
Per-defect, per-model engagement analysis for a single Skill.

For one task (default: data-to-d3) we read every trajectory of both models and,
for each of the skill's confirmed contract inconsistencies, count the runs in
which the agent actually ENGAGED with the defect (mentions it in its own
reasoning, code or tool calls) versus merely being EXPOSED to it (the symbol
appears only inside a tool result, i.e. in a file it happened to read).

  engaged   symbol appears in an assistant-authored block (thinking / text /
            tool_use input)  -> the defect reached the agent's decision making
  exposed   symbol appears only in tool results (file contents, bash output)
  untouched never appears

Usage:  python3 analyse_case.py [task]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict

ROOT = "/workspace/skillEvaluation"

# confirmed contract inconsistencies of data-to-d3, after re-verification
DEFECTS = {
    "D1 version conflict (v6 vs 7.9.0)":
        r"d3\.v7|v7\.9|7\.9\.0|d3@7|vendor/d3|d3/dist",
    "D2 undefined helper (highlightBubble)":
        r"highlightBubble|selectBubble",
    "D3 determinism rule vs force layout":
        r"deterministic|determinism|\.seed\(|fixed tick|tick count|nTicks|tick\(\)",
}


def blocks(path: str):
    """Yield ('assistant'|'tool', text) for every content block of a run."""
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        typ = rec.get("type")
        if isinstance(content, str):
            yield ("assistant" if typ == "assistant" else "tool", content)
            continue
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt in ("thinking", "text"):
                yield ("assistant", b.get("thinking") or b.get("text") or "")
            elif bt == "tool_use":
                yield ("assistant", json.dumps(b.get("input") or {},
                                               ensure_ascii=False))
            elif bt == "tool_result":
                c = b.get("content")
                if isinstance(c, list):
                    yield ("tool", " ".join(
                        x.get("text", "") for x in c if isinstance(x, dict)))
                else:
                    yield ("tool", str(c or ""))


def scan(path: str) -> dict:
    out = defaultdict(lambda: {"assistant": 0, "tool": 0})
    for kind, text in blocks(path):
        if not text:
            continue
        for name, pat in DEFECTS.items():
            if re.search(pat, text, re.I):
                out[name][kind] += 1
    return out


def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else "data-to-d3"
    runs = []
    ds = sorted(glob.glob(os.path.join(
        ROOT, "experiments/deepseek-traces/transcripts/skillbench-25",
        task, "*", "*.jsonl")))
    for p in ds:
        arm, trial = p.split(os.sep)[-2], os.path.splitext(os.path.basename(p))[0]
        runs.append(("deepseek-flash", f"{arm}/{trial}", p))
    hs = sorted(glob.glob(os.path.join(
        ROOT, "haiku45-threeway-20260917/runs", f"{task}__*",
        "attempts/attempt-01/*/cli.stdout.jsonl")))
    for p in hs:
        run = p.split(os.sep)[-5]
        arm, trial = run.split("__")[1], run.split("__")[2]
        runs.append(("claude-haiku", f"{arm}/{trial}", p))

    print(f"task = {task}   runs = {len(runs)}\n")
    per = defaultdict(lambda: defaultdict(list))
    for model, run, path in runs:
        res = scan(path)
        for d in DEFECTS:
            v = res.get(d, {"assistant": 0, "tool": 0})
            state = ("engaged" if v["assistant"] else
                     "exposed" if v["tool"] else "untouched")
            per[d][model].append((run, state, v["assistant"], v["tool"]))

    for d in DEFECTS:
        print("=" * 88)
        print(d)
        for model in ("deepseek-flash", "claude-haiku"):
            items = per[d][model]
            n = len(items)
            c = defaultdict(int)
            for _, s, _, _ in items:
                c[s] += 1
            print(f"  {model:16s} n={n}  engaged={c['engaged']} "
                  f"exposed={c['exposed']} untouched={c['untouched']}")
            for run, s, a, t in items:
                flag = {"engaged": "E", "exposed": "e", "untouched": "."}[s]
                print(f"      {flag} {run:28s} assistant_hits={a:3d} tool_hits={t:3d}")
        print()


if __name__ == "__main__":
    main()
