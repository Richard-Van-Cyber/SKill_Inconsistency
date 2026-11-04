#!/bin/bash
# Robust "wait for the gpt-oss axis, then collect" job.
#
# Replaces the first version after the campus VPN dropped mid-run (2026-10-02, between
# 03:37 and 06:58): the old job treated a failed ssh probe as "0 cells" and would have
# run the finalize path over a dead link and printed ALL DONE anyway.
#
# Behaviour
#   * every 10 min: probe the cell count; a failed probe is reported as such and retried
#   * only finalize when the probe SUCCEEDS and reports >= 441 completed cells
#   * every finalize step must succeed (or the job retries, then exits non-zero)
#   * prints RESULT: DONE only after the local rsync actually landed
set -u
HOST=user@10.0.0.64
SRC=/home/user/project/experiments/wildskills49-gptoss-20261002
COLL=/home/user/project/experiments/wildskills-gptoss-collection
OLOG=/home/user/project/experiments/wildskills49-gptoss-orchestrator
PY=/home/user/project/.venv-benchflow/bin/python
LOCAL=/workspace/skillEvaluation/experiments/wildskills49-gptoss-20261002
PLANNED=441
SSH=(ssh -n -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=2)

probe() {  # prints the completed-cell count, or nothing when unreachable
  "${SSH[@]}" "$HOST" "ls $SRC/runs/*/result.json 2>/dev/null | wc -l" 2>/dev/null | tr -d '[:space:]'
}

echo "[wait] start $(date '+%F %T') — need $PLANNED cells"
n=""
for i in $(seq 1 400); do
  n=$(probe)
  if [ -z "$n" ]; then
    echo "[wait $(date '+%H:%M')] ssh/VPN unreachable — retrying in 10 min"
  else
    echo "[wait $(date '+%H:%M')] terminal=$n/$PLANNED"
    [ "$n" -ge "$PLANNED" ] && break
  fi
  sleep 600
done

if [ -z "$n" ] || [ "${n:-0}" -lt "$PLANNED" ]; then
  echo "RESULT: NOT FINALIZED — run never observed $PLANNED/$PLANNED cells (last probe: '${n:-unreachable}')"
  exit 2
fi

echo "[finalize] study complete ($n/$PLANNED) at $(date '+%F %T'); settling 120 s"
sleep 120

for attempt in 1 2 3 4 5; do
  echo "[finalize] attempt $attempt: server-side statistics"
  if "${SSH[@]}" "$HOST" "cd $SRC/tools && $PY build_manifest_all_axes.py /home/user/project/experiments $COLL >/dev/null 2>&1 \
      && $PY aggregate_axis.py $COLL/manifest.csv gptoss > $COLL/gptoss-axis.txt 2>&1 \
      && $PY paper_stats_all_axes.py $COLL/manifest.csv $COLL > $COLL/paper_stats.txt 2>&1 \
      && test -s $COLL/paper_stats.json" 2>/dev/null; then
    echo "[finalize] server statistics ok"
    break
  fi
  echo "[finalize] attempt $attempt failed (ssh or analysis error); retrying in 5 min"
  sleep 300
  [ "$attempt" = 5 ] && { echo "RESULT: NOT FINALIZED — server-side analysis failed"; exit 3; }
done

for attempt in 1 2 3 4 5; do
  echo "[finalize] attempt $attempt: rsync results to this Mac"
  if bash "$LOCAL/pull_results.sh"; then
    echo "RESULT: DONE — results are in $LOCAL (runs/, reports/)"
    exit 0
  fi
  echo "[finalize] rsync attempt $attempt failed; retrying in 5 min"
  sleep 300
done
echo "RESULT: NOT FINALIZED — rsync failed"
exit 4
