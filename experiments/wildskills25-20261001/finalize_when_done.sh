#!/bin/bash
# Wait for every wildskills13 study driver to exit, then pull the runs and regenerate all
# analysis artifacts. Safe to run repeatedly: it only reads from the server.
#
# Usage:  bash finalize_when_done.sh [max_minutes]
set -u
REPO=/workspace/skillEvaluation
HOST=10.0.0.64
MAXMIN=${1:-240}
STUDIES="wildskills25-20261001a wildskills25-20261001b wildskills25-20261001c wildskills25-placebo-20261001"

cd "$REPO" || exit 1
echo "[watch] waiting for the study drivers to finish (max ${MAXMIN} min)…"
for i in $(seq 1 "$MAXMIN"); do
  # The pattern is assembled on the remote from a variable so this ssh command line cannot
  # match it (pgrep -f self-match trap).
  n=$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST" \
      'P=wildskills; pgrep -cf "${P}_run.py --serve"' 2>/dev/null || echo '?')
  if [ "$n" = "0" ]; then echo "[watch] all drivers exited after ${i} min"; break; fi
  if [ $((i % 10)) -eq 0 ]; then echo "[watch] ${i} min elapsed, drivers still up: $n"; fi
  sleep 60
done

echo "[sync] pulling runs from the server"
for s in $STUDIES; do
  rsync -a --exclude '__pycache__' --exclude 'api' \
        "$HOST:/home/user/project/experiments/$s/runs" "experiments/$s/" 2>/dev/null
  printf "  %-32s %s cells\n" "$s" "$(ls experiments/$s/runs 2>/dev/null | wc -l | tr -d ' ')"
done

echo "[analyse] regenerating datasets and reports"
python3 experiments/wildskills25-20261001/analyze_mechanism.py \
    --studies wildskills25-20261001a,wildskills25-20261001b,wildskills25-20261001c
python3 experiments/wildskills25-20261001/analyze_checks.py \
    --studies wildskills25-20261001a,wildskills25-20261001b,wildskills25-20261001c
python3 experiments/wildskills13-20260929/consolidate13.py \
    --studies wildskills25-20261001a,wildskills25-20261001b,wildskills25-20261001c \
    --placebo-study wildskills25-placebo-20261001
echo "[done] artifacts under experiments/wildskills25-dataset/"
