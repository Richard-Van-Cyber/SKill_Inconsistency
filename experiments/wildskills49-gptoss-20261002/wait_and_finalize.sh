#!/bin/bash
# Block until the gpt-oss:20b wildskills axis finishes, then collect everything.
#
#   1. poll the server until all 441 canonical cells are terminal (or the orchestrator
#      writes its DONE marker)
#   2. run the four-axis paper statistics ON THE SERVER (the full experiments tree is there)
#   3. pull runs/ + reports/ + orchestrator logs back to this Mac (incremental rsync)
#   4. print a local summary
#
# Intended to run as a background job: it is the only thing that needs to poll, so the
# session does not have to.
set -u
HOST=user@10.0.0.64
SRC=/home/user/project/experiments/wildskills49-gptoss-20261002
COLL=/home/user/project/experiments/wildskills-gptoss-collection
LOG=/home/user/project/experiments/wildskills49-gptoss-orchestrator
PY=/home/user/project/.venv-benchflow/bin/python
LOCAL=/workspace/skillEvaluation/experiments/wildskills49-gptoss-20261002
PLANNED=441

terminal() {
  ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$HOST" \
    "ls $SRC/runs/*/result.json 2>/dev/null | wc -l; test -f $LOG/DONE && echo DONE || echo RUNNING" \
    2>/dev/null | tr '\n' ' '
}

echo "[wait] start $(date '+%F %T') — waiting for $PLANNED cells"
for i in $(seq 1 200); do
  info=$(terminal)
  n=$(echo "$info" | awk '{print $1}')
  marker=$(echo "$info" | awk '{print $2}')
  echo "[wait $(date '+%H:%M')] terminal=${n:-?}/$PLANNED ${marker:-}"
  if [ "${n:-0}" -ge "$PLANNED" ] || [ "$marker" = "DONE" ]; then
    echo "[wait] study finished at $(date '+%F %T')"
    break
  fi
  sleep 600
done

echo "[finalize] four-axis paper statistics on the server $(date '+%F %T')"
ssh -n -o BatchMode=yes -o ConnectTimeout=15 "$HOST" \
  "cd $SRC/tools && $PY build_manifest_all_axes.py /home/user/project/experiments $COLL >/dev/null 2>&1; \
   $PY aggregate_axis.py $COLL/manifest.csv gptoss > $COLL/gptoss-axis.txt 2>&1; \
   $PY paper_stats_all_axes.py $COLL/manifest.csv $COLL > $COLL/paper_stats.txt 2>&1; \
   tail -3 $COLL/gptoss-axis.txt; echo '--- paper stats (gptoss block) ---'; \
   sed -n '/gptoss/,\$p' $COLL/paper_stats.txt | head -20"

echo "[finalize] pulling results to this Mac $(date '+%F %T')"
bash "$LOCAL/pull_results.sh"

echo "[finalize] local report"
python3 - "$LOCAL" <<'PYEOF'
import collections, glob, json, os, re, statistics, sys
dst = sys.argv[1]
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
per, st, batch = collections.defaultdict(list), collections.Counter(), collections.defaultdict(list)
for p in glob.glob(os.path.join(dst, "runs", "*", "result.json")):
    cell = p.split("/runs/")[1].split("/")[0]
    if not CANON.match(cell):
        continue
    d = json.load(open(p))
    st[d.get("status")] += 1
    if isinstance(d.get("score"), (int, float)):
        per[cell.split("__")[1]].append(d["score"])
term = sum(v for k, v in st.items() if k not in ("agent_running", "verifying"))
lines = [f"terminal={term}/441  statuses={dict(st)}"]
for arm in ("NoSkill", "OriginalSkill", "FixedSkill"):
    xs = per.get(arm, [])
    lines.append(f"  {arm:<14} n={len(xs):<3} mean={statistics.mean(xs):.4f}" if xs else f"  {arm}: n=0")
open(os.path.join(dst, "reports", "local-summary.txt"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
PYEOF
echo "[finalize] ALL DONE $(date '+%F %T')"
