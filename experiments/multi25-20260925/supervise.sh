#!/usr/bin/env bash
# Unattended supervisor for the multi25 study.
#
#  1. wait for the current phase-1a driver (6 ready tasks) to exit
#  2. wait for the remaining image builds to finish
#  3. run the P11 feasibility gate over all 15 tasks
#  4. run phase 1b: NoSkill+OriginalSkill for the 9 remaining tasks
#
# Safe to re-run: the driver skips cells that already have a graded/verifier_error
# result, and the gate skips tasks whose image is still missing (reporting that).
set -uo pipefail
REPO=/home/user/project
STUDY=$REPO/experiments/multi25-20260925
RS=$STUDY/runner-source
PY=$REPO/.venv-benchflow/bin/python3
LOG=/tmp/multi25_supervisor.log

REMAIN="exceltable-in-ppt glm-lake-mendota manufacturing-equipment-maintenance \
manufacturing-fjsp-optimization powerlifting-coef-calc protein-expression-analysis \
sec-financial-report spring-boot-jakarta-migration weighted-gdp-calc"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "supervisor start"

# 1. wait for phase 1a
while pgrep -f "multi25_run.py" >/dev/null 2>&1; do sleep 60; done
log "phase 1a driver finished"

# 2. wait for builds
while pgrep -f "build_images.sh" >/dev/null 2>&1; do sleep 60; done
log "builds finished: $(grep -E '^====' /tmp/build25_run.log | tail -1)"

# 3. P11 feasibility gate (task package lives in the study's inputs/)
cd "$STUDY"
if [ -f "$REPO/feasibility_gate.sh" ]; then
  log "running P11 gate"
  # keep this list in step with inputs/selected_tasks (powerlifting-coef-calc and
  # spring-boot-jakarta-migration were replaced: their own Dockerfiles fetch from
  # github.com, which this sandbox cannot reach)
  bash "$REPO/feasibility_gate.sh" citation-check earthquake-plate-calculation \
      energy-ac-optimal-power-flow exceltable-in-ppt glm-lake-mendota hvac-control \
      lab-unit-harmonization manufacturing-equipment-maintenance \
      manufacturing-fjsp-optimization flood-risk-analysis protein-expression-analysis \
      r2r-mpc-control sec-financial-report offer-letter-generator \
      weighted-gdp-calc >>"$LOG" 2>&1
  log "P11 gate done"
else
  log "WARNING: feasibility_gate.sh not found at $REPO; skipping gate"
fi

# 4. phase 1b -- run the full 15-task set; the driver skips cells that already have a
# graded/verifier_error result, so this also picks up any straggler from phase 1a.
# Wait for any manually-started phase-1 driver first (we may have started one for the
# tasks whose images were ready, to overlap with the remaining builds); running two
# drivers over the same cell set would double-schedule cells.
while pgrep -f "multi25_run.py" >/dev/null 2>&1; do sleep 60; done
log "no other phase-1 driver running; starting phase 1b"
cd "$RS"
log "phase 1b: NoSkill+OriginalSkill for all 15 tasks (workers=6)"
"$PY" multi25_run.py --arms NoSkill,OriginalSkill --workers 6 \
    >"$STUDY/phase1_rest.log" 2>&1
log "phase 1b finished rc=$?"
log "supervisor done"
