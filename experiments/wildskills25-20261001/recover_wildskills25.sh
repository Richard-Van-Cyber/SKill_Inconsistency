#!/bin/bash
# wildskills25 — sequential cell recovery (server side, run detached).
#
# Why sequential: with several studies running at once, each study's container/network sweep deletes
# the other studies' freshly created networks ("failed to set up container networking: network ... not
# found"), which turned 13+ cells into agent_error. One study at a time removes that race.
#
# For each study: find non-graded cells -> move their stale cell dirs aside (so a cell stuck in
# `agent_running` is treated as pending again) -> run the driver for exactly those cells -> wait.
# Task names listed in $LOG/HOLD.txt (one per line) are skipped until their fix lands.
set -u
ROOT=/home/user/project
EXP=$ROOT/experiments
PY=$ROOT/.venv-benchflow/bin/python
LOG=$EXP/wildskills25-orchestrator
HOLD=$LOG/HOLD.txt
STUDIES="wildskills25-20261001a wildskills25-20261001b wildskills25-20261001c wildskills25-placebo-20261001"
mkdir -p "$LOG"

pending() {
  "$PY" - "$EXP" "$1" "$HOLD" <<'PYEOF'
import glob, json, os, sys
exp, study, hold = sys.argv[1], sys.argv[2], sys.argv[3]
held = set()
if os.path.isfile(hold):
    held = {l.strip() for l in open(hold) if l.strip() and not l.startswith('#')}
import re
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
for p in sorted(glob.glob(f"{exp}/{study}/runs/*/*/result.json")):
    cell = p.split("/runs/")[1].split("/")[0]
    # ignore the driver's own backup dirs: "<cell>.stale-<ts>" and "<cell>__<timestamp>"
    if not CANON.match(cell):
        continue
    try:
        d = json.load(open(p))
    except Exception:
        continue
    st = d.get("status")
    if st == "graded":
        continue
    if cell.split("__")[0] in held:
        continue
    print(f"{cell}\t{st}")
PYEOF
}

log() { echo "[$(date +%F' '%T)] $*" >> "$LOG/recover.log"; }
log "sequential recovery start"

for round in $(seq 1 120); do
  if [ -f "$LOG/STOP" ]; then log "STOP file found"; break; fi
  work=0
  for s in $STUDIES; do
    if pgrep -f "experiments/$s/runner-source/wildskills_run.py --serve" >/dev/null 2>&1; then
      log "$s still has a driver; waiting"; work=1; continue
    fi
    LIST=$(pending "$s" | cut -f1 | tr '\n' ',' | sed 's/,$//')
    [ -z "$LIST" ] && continue
    n=$(echo "$LIST" | tr ',' '\n' | wc -l | tr -d ' ')
    for c in $(echo "$LIST" | tr ',' ' '); do
      d="$EXP/$s/runs/$c"
      case "$c" in *"__"*"__"r[0-9]*) [ -d "$d" ] && mv "$d" "${d}.stale-$(date +%s)" 2>/dev/null;; esac
    done
    log "$s: running $n cell(s): $LIST"
    ( cd "$ROOT" && WS_STUDY_NAME="$s" WS_REPEATS=3 \
      "$PY" -u "$EXP/$s/runner-source/wildskills_run.py" --serve --workers 2 --cells "$LIST" \
      >> "$EXP/$s/batch.log" 2>&1 )
    work=1
  done
  if [ "$work" -eq 0 ]; then
    log "nothing left to recover"
    date > "$LOG/DONE"
    break
  fi
  sleep 45      # let an active driver finish / avoid hot-looping while cells run
done

{
  echo "recovery finished $(date)"
  for s in $STUDIES; do
    echo "  $s: $(pending "$s" | wc -l | tr -d ' ') non-graded cell(s) left (held-back tasks excluded)"
  done
} >> "$LOG/recover.log"
