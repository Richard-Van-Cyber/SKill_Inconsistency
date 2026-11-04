#!/usr/bin/env python3
"""Parse the SkillsBench paper-v1 withskills runs (haiku-4-5) into a per-task table.

Source: hf_downloads/submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3
Each run dir: result.json (reward, timing), trajectory/legacy_agent/claude-code.txt (JSONL w/ usage)
"""
import json, os, glob, collections, statistics, sys

ROOT = "hf_downloads/submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3"

def usage_from_log(path):
    """Sum usage over assistant messages; claude-code JSONL repeats cumulative usage, so take per-message usage and sum."""
    tot_in = tot_out = tot_cache_r = tot_cache_w = 0
    calls = 0
    ok = False
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                u = None
                if o.get("type") == "assistant":
                    u = (o.get("message") or {}).get("usage")
                elif o.get("type") == "result":
                    u = o.get("usage")
                    if u:
                        # result line is aggregate; prefer it if present
                        ok = True
                        tot_in = u.get("input_tokens", 0) or 0
                        tot_out = u.get("output_tokens", 0) or 0
                        tot_cache_r = u.get("cache_read_input_tokens", 0) or 0
                        tot_cache_w = u.get("cache_creation_input_tokens", 0) or 0
                        calls = o.get("num_turns") or 0
                        continue
                if not u:
                    continue
                ok = True
                calls += 1
                tot_in += u.get("input_tokens", 0) or 0
                tot_out += u.get("output_tokens", 0) or 0
                tot_cache_r += u.get("cache_read_input_tokens", 0) or 0
                tot_cache_w += u.get("cache_creation_input_tokens", 0) or 0
    except FileNotFoundError:
        return None
    if not ok:
        return None
    return dict(calls=calls, input_tokens=tot_in, output_tokens=tot_out,
                cache_read=tot_cache_r, cache_write=tot_cache_w,
                total_tokens=tot_in + tot_out + tot_cache_r + tot_cache_w)

def main():
    runs = []
    for d in sorted(glob.glob(os.path.join(ROOT, "*__paper-v1-*"))):
        name = os.path.basename(d)
        task = name.split("__")[0]
        try:
            res = json.load(open(os.path.join(d, "result.json")))
        except Exception as e:
            print("skip", name, e, file=sys.stderr); continue
        log = os.path.join(d, "trajectory", "legacy_agent", "claude-code.txt")
        u = usage_from_log(log)
        runs.append(dict(
            run=name, task=task,
            reward=(res.get("rewards") or {}).get("reward"),
            error=res.get("error"), verifier_error=res.get("verifier_error"),
            partial=res.get("partial_trajectory"),
            t_total=(res.get("timing") or {}).get("total"),
            t_env=(res.get("timing") or {}).get("environment_setup"),
            t_agent=(res.get("timing") or {}).get("agent_execution"),
            t_verifier=(res.get("timing") or {}).get("verifier"),
            usage=u,
        ))
    json.dump(runs, open("/tmp/baseline_runs.json", "w"), indent=1)
    print(f"parsed {len(runs)} runs; tasks={len(set(r['task'] for r in runs))}")
    print(f"runs with usage: {sum(1 for r in runs if r['usage'])}")

if __name__ == "__main__":
    main()
