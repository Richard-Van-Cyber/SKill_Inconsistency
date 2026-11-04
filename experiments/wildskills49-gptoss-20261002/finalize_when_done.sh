#!/bin/bash
# Waits for the gpt-oss:20b axis to finish, then builds the all-axes manifest and the
# per-axis aggregate report for the gptoss axis.
#
# Written as a separate watcher so the running orchestrator does not have to be restarted:
# it polls the orchestrator's DONE marker (or the terminal cell count) and only then analyses.
#   report -> $OUT/SUMMARY.md, $OUT/manifest.csv
#   log    -> $LOG/finalize.log
set -u
ROOT=/home/user/project
EXP=$ROOT/experiments
PY=$ROOT/.venv-benchflow/bin/python
STUDY=wildskills49-gptoss-20261002
TOOLS=$EXP/$STUDY/tools
LOG=$EXP/wildskills49-gptoss-orchestrator
OUT=$EXP/wildskills-gptoss-collection
PLANNED=441

terminal() {
  "$PY" - "$EXP" "$STUDY" <<'PYEOF'
import glob, json, re, sys
exp, study = sys.argv[1], sys.argv[2]
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
n = 0
for p in glob.glob(f"{exp}/{study}/runs/*/result.json"):
    cell = p.split("/runs/")[1].split("/")[0]
    if not CANON.match(cell):
        continue
    try:
        st = json.load(open(p)).get("status")
    except Exception:
        continue
    if st and st not in ("agent_running", "verifying"):
        n += 1
print(n)
PYEOF
}

echo "[$(date +%F' '%T)] finalize watcher start (pid $$) planned=$PLANNED" >> "$LOG/finalize.log"
for round in $(seq 1 2000); do
  n=$(terminal)
  if [ -f "$LOG/DONE" ] || [ "$n" -ge "$PLANNED" ]; then
    echo "[$(date +%F' '%T)] study finished ($n/$PLANNED) — running analysis" >> "$LOG/finalize.log"
    break
  fi
  sleep 300
done

mkdir -p "$OUT"
cd "$TOOLS" || exit 1
{
  echo "=== manifest build $(date) ==="
  "$PY" build_manifest_all_axes.py "$EXP" "$OUT"
  echo
  echo "=== gptoss axis aggregate $(date) ==="
  "$PY" aggregate_axis.py "$OUT/manifest.csv" gptoss
  echo
  echo "=== cross-axis (all) $(date) ==="
  "$PY" aggregate_axis.py "$OUT/manifest.csv" all
} >> "$LOG/finalize.log" 2>&1

# per-arm score table for the gptoss axis only, easy to paste into a report
"$PY" - "$EXP/$STUDY" "$OUT/gptoss-report.md" >> "$LOG/finalize.log" 2>&1 <<'PYEOF'
import collections, glob, json, re, statistics, sys
study, out = sys.argv[1], sys.argv[2]
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
ARMS = ["NoSkill", "OriginalSkill", "FixedSkill"]
per = collections.defaultdict(list)
status = collections.Counter()
for p in glob.glob(study + "/runs/*/result.json"):
    cell = p.split("/runs/")[1].split("/")[0]
    if not CANON.match(cell):
        continue
    d = json.load(open(p))
    status[d.get("status")] += 1
    if isinstance(d.get("score"), (int, float)):
        per[cell.split("__")[1]].append(d["score"])
L = ["# wildskills — gpt-oss:20b axis (49 tasks x 3 conditions x 3 trials = 441 cells)", ""]
L.append("status: " + ", ".join(f"{k}={v}" for k, v in sorted(status.items())))
# each arm schedules 49 tasks * 3 trials = 147 cells; ITT counts a missing/failed cell as 0
L += ["", "| arm | cells scored | mean score (scored) | mean score (ITT, /147) |", "|---|---|---|---|"]
for a in ARMS:
    xs = per.get(a, [])
    L.append(f"| {a} | {len(xs)} | {statistics.mean(xs):.4f} | {sum(xs) / 147:.4f} |" if xs
             else f"| {a} | 0 | — | 0.0000 |")
open(out, "w").write("\n".join(L) + "\n")
print("wrote", out)
PYEOF

echo "[$(date +%F' '%T)] finalize done" >> "$LOG/finalize.log"
