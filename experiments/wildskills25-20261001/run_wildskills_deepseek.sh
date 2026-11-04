#!/bin/bash
# wildskills — DeepSeek axis: run the two new batches (batch13: 14 tasks, batch25: 23 tasks)
# with model deepseek-flash, three arms x 3 trials, same budget as the haiku cells.
#
# Design (learned the hard way on the haiku side):
#   * ONE study at a time, and it also waits until no other project driver is running first.  Running
#     several studies concurrently makes each study's container/network sweep delete the others'
#     freshly created docker networks ("failed to setup container networking: network ... not found"),
#     which turned 13+ haiku cells into agent_error.
#   * resumes: a study whose driver died while cells remain is relaunched; completed cells are skipped.
#   * only canonical cell dirs count (the driver keeps "<cell>.stale-<ts>" / "<cell>__<ts>" backups).
#   * STOP switch: touch $LOG/STOP ; completion: $LOG/DONE + $LOG/SUMMARY.txt
#   * at the end it produces the dataset for the DeepSeek axis under experiments/wildskills-deepseek-dataset/
set -u
ROOT=/home/user/project
EXP=$ROOT/experiments
PY=$ROOT/.venv-benchflow/bin/python
TOOLS=$EXP/wildskills25-tools
LOG=$EXP/wildskills-deepseek-orchestrator
mkdir -p "$LOG"

STUDIES="wildskills13-deepseek-20260929 wildskills25-deepseek-20261001"
declare -A TASKS
for s in $STUDIES; do TASKS[$s]=$(cat "$EXP/$s/WS_TASKS.txt"); done

planned() { echo $(( $(echo "${TASKS[$1]}" | tr ',' '\n' | wc -l) * 9 )); }
terminal() {
  "$PY" - "$EXP" "$1" <<'PYEOF'
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

log "deepseek orchestrator start (pid $$)  studies: $STUDIES"
for round in $(seq 1 400); do
  if [ -f "$LOG/STOP" ]; then log "STOP file found"; break; fi
  all_done=1
  for s in $STUDIES; do
    pl=$(planned "$s"); n=$(terminal "$s")
    if [ "$n" -ge "$pl" ]; then continue; fi
    all_done=0
    if pgrep -f "experiments/$s/runner-source/wildskills_run.py --serve" >/dev/null 2>&1; then
      continue
    fi
    # wait until every other driver is gone, so no two studies sweep each other's networks
    while pgrep -f "[w]ildskills_run.py --serve" >/dev/null 2>&1; do
      [ -f "$LOG/STOP" ] && break
      sleep 45
    done
    log "starting $s  done=$n/$pl  model=deepseek-flash workers=3"
    ( cd "$ROOT" && WS_STUDY_NAME="$s" WS_TASKS="${TASKS[$s]}" WS_REPEATS=3 WS_MODEL=deepseek-flash \
      setsid nohup "$PY" -u "$EXP/$s/runner-source/wildskills_run.py" --serve --workers 3 \
      >> "$EXP/$s/batch.log" 2>&1 < /dev/null & )
    sleep 15
  done
  if [ "$all_done" -eq 1 ]; then
    log "ALL DEEPSEEK STUDIES COMPLETE"
    date > "$LOG/DONE"
    break
  fi
  sleep 60
done

{
  echo "deepseek orchestration finished $(date)"
  for s in $STUDIES; do echo "  $s: $(terminal "$s")/$(planned "$s") terminal cells"; done
} > "$LOG/SUMMARY.txt"
cat "$LOG/SUMMARY.txt" >> "$LOG/orchestrator.log"

# dataset for the DeepSeek axis (no placebo on this axis)
log "running analysis for the deepseek axis"
( cd "$TOOLS" && "$PY" consolidate13.py \
    --studies "wildskills13-deepseek-20260929,wildskills25-deepseek-20261001" \
    --placebo-study wildskills-deepseek-placebo-none \
    --out "$EXP/wildskills-deepseek-dataset" >> "$LOG/analyze.log" 2>&1 )
log "analysis done -> $EXP/wildskills-deepseek-dataset"
