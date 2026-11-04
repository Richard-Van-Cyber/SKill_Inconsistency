#!/bin/bash
# wildskills — gpt-oss:20b axis: all 49 tasks x 3 arms x 3 trials = 441 cells.
#
# Model plumbing (validated by smoke cells):
#   Claude Code CLI -> per-run credential proxy (group 'ollama') -> one of two local ollama
#   containers, chosen deterministically per cell by the proxy:
#     11435 = GPU 1 (A100-80GB, OLLAMA_CONTEXT_LENGTH=262144, NUM_PARALLEL=5)
#     11436 = GPU 0 (A100-40GB, OLLAMA_CONTEXT_LENGTH=98304,  NUM_PARALLEL=3)
#   Both cards were verified warm at ~85 tok/s single-stream, and 8-way parallel
#   (5+3) at ~44/~24 tok/s per stream, aggregate ~290 tok/s.
#
#   8 workers == 5 + 3 parallel slots, i.e. the largest concurrency the two cards can serve.
#
# One study at a time; a study whose driver died is relaunched; only canonical cells count.
# STOP: touch $LOG/STOP   DONE: $LOG/DONE   summary: $LOG/SUMMARY.txt
set -u
ROOT=/home/user/project
EXP=$ROOT/experiments
PY=$ROOT/.venv-benchflow/bin/python
LOG=$EXP/wildskills49-gptoss-orchestrator
mkdir -p "$LOG"

STUDY=wildskills49-gptoss-20261002
MODEL=gpt-oss-20b
WORKERS=${GPTOSS_WORKERS:-8}
TASKS=$(cat "$EXP/$STUDY/WS_TASKS.txt")
PLANNED=$(( $(echo "$TASKS" | tr ',' '\n' | wc -l) * 9 ))

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
log() { echo "[$(date +%F' '%T)] $*" >> "$LOG/orchestrator.log"; }

# Driver detection MUST be anchored at the interpreter path: a plain
# `pgrep -f "wildskills_run.py --serve"` also matches the ssh `bash -c` wrapper that
# launched this orchestrator (its cmdline quotes the pattern), so the orchestrator would
# wait forever for a "foreign driver" that is really its own launcher. Anchoring on ^$PY
# matches only real driver processes.
driver_pid() { pgrep -f "^$PY -u .*runner-source/wildskills_run\.py --serve" 2>/dev/null; }

log "gpt-oss orchestrator start (pid $$) study=$STUDY planned=$PLANNED model=$MODEL workers=$WORKERS"
for round in $(seq 1 600); do
  [ -f "$LOG/STOP" ] && { log "STOP file found"; break; }
  n=$(terminal)
  if [ "$n" -ge "$PLANNED" ]; then
    log "STUDY COMPLETE ($n/$PLANNED)"
    date > "$LOG/DONE"
    break
  fi
  if driver_pid | grep -q .; then
    sleep 180
    continue
  fi
  # guard: the study must honour WS_MODEL, else it silently runs another axis
  if ! grep -q "os.environ.get('WS_MODEL'" "$EXP/$STUDY/runner-source/wildskills_config.py"; then
    log "ABORT: wildskills_config.py does not honour WS_MODEL"
    date > "$LOG/DONE"
    break
  fi
  log "starting $STUDY  done=$n/$PLANNED  workers=$WORKERS"
  ( cd "$ROOT" && WS_STUDY_NAME="$STUDY" WS_TASKS="$TASKS" WS_REPEATS=3 WS_MODEL="$MODEL" \
    setsid nohup "$PY" -u "$EXP/$STUDY/runner-source/wildskills_run.py" --serve --workers "$WORKERS" \
    >> "$EXP/$STUDY/batch.log" 2>&1 < /dev/null & )
  sleep 30
done

{
  echo "gpt-oss orchestration finished $(date)"
  echo "  $STUDY: $(terminal)/$PLANNED terminal cells"
} > "$LOG/SUMMARY.txt"
cat "$LOG/SUMMARY.txt" >> "$LOG/orchestrator.log"
log "done"
