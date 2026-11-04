#!/bin/bash
# wildskills — Qwen axis: run batch-25 (23 tasks) with the local GPU ollama model qwen3.6:35b.
#
# Model plumbing (already validated by a smoke cell that graded 0.25):
#   Claude Code CLI -> per-run credential proxy (group 'ollama', http://127.0.0.1:11435, timeout 3600s)
#   -> ollama_gpu container --gpus all -> qwen3.6:35b (A100-80GB, context 262144, ~130 tok/s warm)
#
# Same three arms x 3 trials and the same per-run budget as the haiku/deepseek axes.
# One study at a time; a study whose driver died is relaunched; canonical cells only.
# STOP: touch $LOG/STOP   DONE: $LOG/DONE   summary: $LOG/SUMMARY.txt
set -u
ROOT=/home/user/project
EXP=$ROOT/experiments
PY=$ROOT/.venv-benchflow/bin/python
TOOLS=$EXP/wildskills25-tools
LOG=$EXP/wildskills-ollama-orchestrator
mkdir -p "$LOG"

STUDY=wildskills25-ollama-20260930
# 3 slots on the 80GB card + 2 on the 40GB card
WORKERS=${OLLAMA_WORKERS:-5}
TASKS=$(cat "$EXP/$STUDY/WS_TASKS.txt")
PLANNED=$(( $(echo "$TASKS" | tr ',' '\n' | wc -l) * 9 ))

terminal() {
  "$PY" - "$EXP" "$STUDY" <<'PYEOF'
import glob, json, re, sys
exp, study = sys.argv[1], sys.argv[2]
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
n = 0
for p in glob.glob(f"{exp}/{study}/runs/*/*/result.json"):
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
log() { echo "[$(date +%F' '%T)] $*" >> "$LOG/orchestrator.log"; }

log "qwen orchestrator start (pid $$) study=$STUDY planned=$PLANNED model=qwen3.6:35b"
for round in $(seq 1 400); do
  [ -f "$LOG/STOP" ] && { log "STOP file found"; break; }
  n=$(terminal)
  if [ "$n" -ge "$PLANNED" ]; then
    log "STUDY COMPLETE ($n/$PLANNED)"
    date > "$LOG/DONE"
    break
  fi
  if pgrep -f "experiments/$STUDY/runner-source/wildskills_run.py --serve" >/dev/null 2>&1; then
    sleep 120
    continue
  fi
  log "starting $STUDY  done=$n/$PLANNED  workers=$WORKERS"
  ( cd "$ROOT" && WS_STUDY_NAME="$STUDY" WS_TASKS="$TASKS" WS_REPEATS=3 WS_MODEL=qwen3.6-35b \
    setsid nohup "$PY" -u "$EXP/$STUDY/runner-source/wildskills_run.py" --serve --workers "$WORKERS" \
    >> "$EXP/$STUDY/batch.log" 2>&1 < /dev/null & )
  sleep 20
done

{
  echo "qwen orchestration finished $(date)"
  echo "  $STUDY: $(terminal)/$PLANNED terminal cells"
} > "$LOG/SUMMARY.txt"
cat "$LOG/SUMMARY.txt" >> "$LOG/orchestrator.log"

log "running analysis for the qwen axis"
( cd "$TOOLS" && "$PY" build_manifest.py "$EXP" "$EXP/wildskills-collection" >> "$LOG/analyze.log" 2>&1
  "$PY" aggregate_axis.py "$EXP/wildskills-collection/manifest.csv" all >> "$LOG/analyze.log" 2>&1 )
log "analysis done"
