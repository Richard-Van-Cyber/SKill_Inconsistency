#!/bin/bash
# wildskills — Qwen alignment run: bring the qwen3.6:35b axis up to the SAME 49 tasks as haiku/deepseek.
#
# batch25 (23 tasks) is already done; this fills batch12 (12 tasks) and batch13 (14 tasks):
#   wildskills12-ollama-20260930   10 tasks x 3 arms x 3 trials =  90 cells
#   wildskills12b-ollama-20260930   2 tasks x 2 arms x 3 trials =  12 cells   (no NoSkill arm, as on the other axes)
#   wildskills13-ollama-20260930   14 tasks x 3 arms x 3 trials = 126 cells
#                                                                  ----
#                                                                   228 cells
#
# Model plumbing: Claude Code CLI -> per-run credential proxy (group 'ollama') -> one of two local
# ollama instances, spread deterministically per cell:
#   11435 = GPU 1 (A100-80GB, ctx 262144, parallel 5)   11436 = GPU 0 (A100-40GB, ctx 98304, parallel 3)
# Studies run one at a time; a dead driver is relaunched; only canonical cells count.
# STOP: touch $LOG/STOP   DONE: $LOG/DONE   SUMMARY: $LOG/SUMMARY.txt
set -u
ROOT=/home/user/project
EXP=$ROOT/experiments
PY=$ROOT/.venv-benchflow/bin/python
TOOLS=$EXP/wildskills25-tools
LOG=$EXP/wildskills-ollama-align-orchestrator
mkdir -p "$LOG"

STUDIES="wildskills12-ollama-20260930 wildskills12b-ollama-20260930 wildskills13-ollama-20260930"
declare -A PLANNED=( [wildskills12-ollama-20260930]=90
                     [wildskills12b-ollama-20260930]=12
                     [wildskills13-ollama-20260930]=126 )
declare -A ARMSOPT=(  [wildskills12-ollama-20260930]=""
                      [wildskills12b-ollama-20260930]="--arms OriginalSkill,FixedSkill"
                      [wildskills13-ollama-20260930]="" )
declare -A WORKERS=(  [wildskills12-ollama-20260930]=8
                      [wildskills12b-ollama-20260930]=2
                      [wildskills13-ollama-20260930]=8 )

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

log "qwen alignment start (pid $$) studies: $STUDIES"
for round in $(seq 1 500); do
  [ -f "$LOG/STOP" ] && { log "STOP file found"; break; }
  all_done=1
  for s in $STUDIES; do
    pl=${PLANNED[$s]}; n=$(terminal "$s")
    if [ "$n" -ge "$pl" ]; then continue; fi
    all_done=0
    if pgrep -f "experiments/$s/runner-source/wildskills_run.py --serve" >/dev/null 2>&1; then
      continue
    fi
    # ONE study at a time: concurrent studies each sweep exited project containers AND networks, so
    # they delete each other's freshly created docker networks (this cost 13+ cells on the haiku
    # batch: "failed to setup container networking: network ... not found").
    while pgrep -f "[w]ildskills_run.py --serve" >/dev/null 2>&1; do
      [ -f "$LOG/STOP" ] && break
      sleep 30
    done
    # guard: the study's runner must take the model name from WS_MODEL. A hardcoded
    # MODEL_CONFIG_NAME silently ran the WRONG model once (a copy of an older API study).
    if ! grep -q "os.environ.get('WS_MODEL'" "$EXP/$s/runner-source/wildskills_config.py"; then
      log "ABORT $s: wildskills_config.py does not honour WS_MODEL — refusing to start"
      date > "$LOG/DONE"
      break 2
    fi
    log "starting $s  done=$n/$pl  workers=${WORKERS[$s]}  arms='${ARMSOPT[$s]}'"
    ( cd "$ROOT" && WS_STUDY_NAME="$s" WS_TASKS="$(cat "$EXP/$s/WS_TASKS.txt")" WS_REPEATS=3 \
      WS_MODEL=qwen3.6-35b setsid nohup "$PY" -u "$EXP/$s/runner-source/wildskills_run.py" \
      --serve --workers "${WORKERS[$s]}" ${ARMSOPT[$s]} >> "$EXP/$s/batch.log" 2>&1 < /dev/null & )
    sleep 20
  done
  if [ "$all_done" -eq 1 ]; then
    log "ALL QWEN ALIGNMENT STUDIES COMPLETE"
    date > "$LOG/DONE"
    break
  fi
  sleep 90
done

{
  echo "qwen alignment finished $(date)"
  for s in $STUDIES; do echo "  $s: $(terminal "$s")/${PLANNED[$s]} terminal cells"; done
} > "$LOG/SUMMARY.txt"
cat "$LOG/SUMMARY.txt" >> "$LOG/orchestrator.log"

log "rebuilding the collection manifest + aggregates"
( cd "$TOOLS" && "$PY" build_manifest.py "$EXP" "$EXP/wildskills-collection" >> "$LOG/analyze.log" 2>&1
  for ax in haiku deepseek qwen; do
    echo "=== $ax" >> "$LOG/analyze.log"
    "$PY" aggregate_axis.py "$EXP/wildskills-collection/manifest.csv" "$ax" >> "$LOG/analyze.log" 2>&1
  done
  echo "=== three-axis on batch25" >> "$LOG/analyze.log"
  "$PY" three_axis.py "$EXP/wildskills-collection/manifest.csv" wildskills25 >> "$LOG/analyze.log" 2>&1 )
log "done"
