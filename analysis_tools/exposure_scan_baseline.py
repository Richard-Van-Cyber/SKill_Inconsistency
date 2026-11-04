#!/usr/bin/env python3
"""Per-finding runtime exposure scan over the SkillsBench paper-v1 with-skills runs.

For every audited task (tasks/<task>/audit_report.json) and every baseline run
(hf_downloads/.../2026-01-29__paper-v1-xiangyi-completed-selected3/<task>__paper-v1-*),
decide for each finding whether its evidence could have entered the agent's context:

    file  - the evidence file itself was read, or bash operated inside that skill dir
    doc   - the skill's SKILL.md was injected via the `Skill` tool
    none  - the skill was never loaded and its files were never touched

This mirrors analysis/audit_tools/exposure_scan.py (which did the same for the
10-task three-way study) but runs over the much larger 68-task paper-v1 corpus.

Output: /tmp/exposure_baseline.json
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import defaultdict

TASKS_GLOB = "tasks/*/audit_report.json"
RUNS_GLOB = (
    "hf_downloads/submissions/skillsbench/v1.1/"
    "claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/"
    "2026-01-29__paper-v1-xiangyi-completed-selected3/*__paper-v1-*"
)

# the harness materialises skills under a directory named `skills`
SKILL_DIR_RE = re.compile(r"/skills/([A-Za-z0-9._+-]+)")
SKILLS_ROOT_RE = re.compile(r"/skills/(.+)$")


def skill_of(rel_path: str) -> str | None:
    """'civ6lib/scripts/hex_utils.py' -> 'civ6lib'"""
    if not rel_path:
        return None
    parts = rel_path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else None


def basename_of(rel_path: str) -> str:
    return rel_path.replace("\\", "/").rsplit("/", 1)[-1]


def norm(s: str) -> str:
    """lowercase and drop every non-alphanumeric char."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def rel_after_skills(path: str) -> str | None:
    """'/logs/agent/sessions/skills/marker/scripts/x.py' -> 'marker/scripts/x.py'"""
    m = SKILLS_ROOT_RE.search(path or "")
    return m.group(1) if m else None


def name_matches(dir_name: str, candidate: str) -> bool:
    """Skill dir name vs the name the agent used.

    The paper-v1 corpus predates some task-package renames (object-counter ->
    object_counter, ffmpeg-keyframe-extraction -> ffmpeg), so fall back to
    normalized equality / containment.
    """
    a, b = norm(dir_name), norm(candidate)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 5 and (a in b or b in a):
        return True
    return False


def frontmatter_name(skill_md: str) -> str | None:
    try:
        with open(skill_md, errors="replace") as fh:
            for _ in range(15):
                line = fh.readline()
                if not line:
                    break
                if line.lower().startswith("name:"):
                    return line.split(":", 1)[1].strip().strip("'\"")
    except OSError:
        return None
    return None


def build_skill_name_map(tasks_root: str = "tasks") -> dict[str, dict[str, str]]:
    """task -> {skill_dir_name: declared_name}"""
    out: dict[str, dict[str, str]] = {}
    for skill_md in sorted(glob.glob(os.path.join(tasks_root, "*", "environment", "skills", "*", "SKILL.md"))):
        parts = skill_md.split(os.sep)
        task, dirname = parts[1], parts[-2]
        nm = frontmatter_name(skill_md) or dirname
        out.setdefault(task, {})[dirname] = nm
    return out


def scan_run(log_path: str) -> dict:
    """Extract skill loads, skill-dir bash hits and read paths from one run log."""
    loaded: set[str] = set()          # Skill tool invocations (declared names)
    bash_skills: set[str] = set()     # skill dirs touched by bash
    read_rel: set[str] = set()        # paths made relative to /skills/
    read_base: set[str] = set()
    n_tool_calls = 0
    n_skill_calls = 0

    with open(log_path, errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") != "assistant":
                continue
            for c in (o.get("message") or {}).get("content") or []:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                n_tool_calls += 1
                name = c.get("name")
                inp = c.get("input") or {}
                if name == "Skill":
                    s = inp.get("skill") or inp.get("name")
                    if s:
                        loaded.add(str(s).split(":")[0].strip())
                        n_skill_calls += 1
                elif name == "Bash":
                    cmd = inp.get("command") or ""
                    for m in SKILL_DIR_RE.finditer(cmd):
                        bash_skills.add(m.group(1))
                elif name in ("Read", "NotebookRead"):
                    fp = inp.get("file_path") or inp.get("notebook_path") or ""
                    if fp:
                        read_base.add(os.path.basename(fp))
                        r = rel_after_skills(fp)
                        if r:
                            read_rel.add(r)

    return dict(loaded=sorted(loaded), bash_skills=sorted(bash_skills),
                read_rel=sorted(read_rel), read_base=sorted(read_base),
                n_tool_calls=n_tool_calls, n_skill_calls=n_skill_calls)


def exposure_for_finding(finding: dict, run: dict, dir2name: dict[str, str]) -> str:
    """file / doc / none for one finding against one run."""
    files = []
    for key in ("source_a", "source_b"):
        ev = (finding.get("evidence") or {}).get(key) or {}
        f = ev.get("file")
        if f:
            files.append(f)
    skills = {skill_of(f) for f in files if skill_of(f)}
    skills.discard(None)

    bash_norm = {norm(x) for x in run["bash_skills"]}

    # ---- file level -------------------------------------------------------
    for f in files:
        fn = f.replace("\\", "/")
        sdir = skill_of(fn)
        if basename_of(fn) in run["read_base"]:
            return "file"
        rest = "/".join(fn.split("/")[1:])
        for rr in run["read_rel"]:
            rr_sdir, _, rr_rest = rr.partition("/")
            if sdir and rr_sdir and name_matches(sdir, rr_sdir) and rest and rr_rest == rest:
                return "file"
    for s in skills:
        if norm(s) in bash_norm or any(name_matches(s, b) for b in run["bash_skills"]):
            return "file"

    # ---- doc level --------------------------------------------------------
    for s in skills:
        declared = dir2name.get(s, s)
        for cand in (s, declared):
            if any(name_matches(cand, l) for l in run["loaded"]):
                return "doc"

    # finding without attributable evidence: doc if the task loaded any skill
    if not skills:
        if run["loaded"]:
            return "doc"
        return "none"
    return "none"


def main() -> None:
    tasks = {}
    for p in sorted(glob.glob(TASKS_GLOB)):
        t = p.split("/")[1]
        tasks[t] = json.load(open(p))
    name_map = build_skill_name_map()

    runs_by_task: dict[str, list[dict]] = defaultdict(list)
    for d in sorted(glob.glob(RUNS_GLOB)):
        task = os.path.basename(d).split("__")[0]
        if task not in tasks:
            continue
        log = os.path.join(d, "trajectory", "legacy_agent", "claude-code.txt")
        try:
            res = json.load(open(os.path.join(d, "result.json")))
        except Exception:
            continue
        scan = scan_run(log) if os.path.exists(log) else dict(
            loaded=[], bash_skills=[], read_rel=[], read_base=[],
            n_tool_calls=0, n_skill_calls=0)
        runs_by_task[task].append(dict(
            run=os.path.basename(d),
            reward=(res.get("rewards") or {}).get("reward"),
            timing=res.get("timing") or {},
            **scan,
        ))

    out = {}
    for task, d in tasks.items():
        runs = runs_by_task.get(task, [])
        findings = d.get("findings") or []
        d2n = name_map.get(task, {})
        recs = []
        for f in findings:
            levels = [exposure_for_finding(f, r, d2n) for r in runs]
            recs.append(dict(
                id=f.get("id"),
                severity=f.get("severity"),
                taxonomy_l2=f.get("taxonomy_l2"),
                confidence=f.get("confidence"),
                blocks_execution=(f.get("agent_impact") or {}).get("blocks_execution"),
                silent=(f.get("agent_impact") or {}).get("produces_silent_error"),
                impact_class=(f.get("agent_impact") or {}).get("impact_class"),
                files=[((f.get("evidence") or {}).get(k) or {}).get("file")
                       for k in ("source_a", "source_b")],
                levels=levels,
                n_file=sum(1 for x in levels if x == "file"),
                n_doc=sum(1 for x in levels if x == "doc"),
                n_none=sum(1 for x in levels if x == "none"),
            ))
        out[task] = dict(
            n_runs=len(runs),
            dir2name=d2n,
            skill_load_runs=sum(1 for r in runs if r["loaded"]),
            findings=recs,
            runs=[{k: v for k, v in r.items() if k != "read_rel"} for r in runs],
        )

    json.dump(out, open("/tmp/exposure_baseline.json", "w"), ensure_ascii=False, indent=1)
    n_f = sum(len(v["findings"]) for v in out.values())
    n_exposed = sum(1 for v in out.values() for f in v["findings"] if f["n_file"] or f["n_doc"])
    n_file = sum(1 for v in out.values() for f in v["findings"] if f["n_file"])
    print(f"tasks={len(out)} runs={sum(v['n_runs'] for v in out.values())} "
          f"findings={n_f} ever_exposed={n_exposed} file_level={n_file}")


if __name__ == "__main__":
    main()
