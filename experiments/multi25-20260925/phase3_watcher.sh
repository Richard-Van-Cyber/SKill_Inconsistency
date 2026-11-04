#!/usr/bin/env bash
# Phase-3 auto-launcher.
#
# Phase 1 (NoSkill + OriginalSkill) runs in one driver; phase 3 (RepairedSkill) can start
# per task as soon as that task's two phase-1 arms are complete, which overlaps the phases
# and shortens the wall clock. Doing that by hand each round is both slow and error-prone,
# so this loop does it: every cycle it finds tasks with NS=3 and OS=3 but RS<3 and starts a
# driver for exactly those cells.
#
# Finished-phase-3 tasks are remembered in a done-list so a task is never launched twice.
# The loop exits when every task in the study has three RepairedSkill cells.
#
#   bash phase3_watcher.sh          # run under setsid nohup
set -uo pipefail

REPO=/home/user/project
STUDY=$REPO/experiments/multi25-20260925
RS=$STUDY/runner-source
PY=$REPO/.venv-benchflow/bin/python3
LOG=/tmp/phase3_watcher.log
LAUNCHED=/tmp/phase3_launched.txt     # tasks already handed to a driver
# Do NOT truncate this file: it is the de-duplication record. Truncating it on start made
# the watcher relaunch a task that already had a driver running, so two drivers raced on
# the same cell directory (both rmtree/mkdir the same path).
touch "$LAUNCHED"

log() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }
log "watcher start"

for cycle in $(seq 1 200); do
  out=$("$PY" - "$STUDY" <<'PY'
import json, glob, sys, collections, os
study = sys.argv[1]
d = collections.defaultdict(lambda: collections.Counter())
for p in glob.glob(os.path.join(study, 'runs', '*', 'result.json')):
    try:
        r = json.load(open(p))
    except Exception:
        continue
    q = (r.get('logical_run_id') or '').split('__')
    if len(q) >= 3:
        d[q[0]][q[1]] += 1
tasks = sorted(os.listdir(os.path.join(study, 'inputs', 'selected_tasks')))
ready, complete = [], 0
for t in tasks:
    a = d.get(t, {})
    ns, os_, rs = a.get('NoSkill', 0), a.get('OriginalSkill', 0), a.get('RepairedSkill', 0)
    if ns == 3 and os_ == 3 and rs < 3:
        ready.append(t)
    if rs == 3:
        complete += 1
print(','.join(ready))
print(complete)
print(len(tasks))
PY
)
  ready=$(echo "$out" | sed -n 1p)
  complete=$(echo "$out" | sed -n 2p)
  total=$(echo "$out" | sed -n 3p)
  log "cycle $cycle: complete=$complete/$total ready=[${ready:-none}]"

  if [ "${complete:-0}" = "${total:-0}" ] && [ -z "$ready" ]; then
    log "all tasks have 3 RepairedSkill cells -> watcher done"
    break
  fi

  if [ -n "$ready" ]; then
    cells=""
    newlaunch=""
    for t in $(echo "$ready" | tr ',' ' '); do
      grep -qx "$t" "$LAUNCHED" && continue
      echo "$t" >> "$LAUNCHED"
      newlaunch="$newlaunch $t"
      for r in 1 2 3; do cells="${cells:+$cells,}${t}__RepairedSkill__r${r}"; done
    done
    if [ -n "$cells" ]; then
      # Launch DETACHED and keep looping. Waiting for the batch here serialised the phases:
      # a slow task (energy-ac and glm allow 3600 s per cell) blocked every other task that
      # became eligible meanwhile. Each task has its own disjoint --cells set, so several
      # phase-3 drivers can safely run at once.
      log "launching phase 3 for:$newlaunch"
      ( cd "$RS" && setsid nohup "$PY" multi25_run.py --arms RepairedSkill \
          --cells "$cells" --workers 3 >>"$STUDY/phase3_watcher_runs.log" 2>&1 < /dev/null & )
    fi
  fi
  sleep 180
done
log "watcher exit"
