#!/usr/bin/env bash
# Wait for the 10-task wildskills DeepSeek study to finish, then launch the
# 225-cell skillbench DeepSeek study (25 tasks x 3 arms x 3 trials, 3 workers).
#
# Run from the client; it drives the server over ssh. Safe to re-run: the launch
# is skipped if the target study already has a driver process alive.
set -uo pipefail

H=10.0.0.64
CUR=/home/user/project/experiments/wildskills-deepseek-20260927
NEW=/home/user/project/experiments/skillbench-deepseek-20260927
PY=/home/user/project/.venv-benchflow/bin/python
S="ssh -o BatchMode=yes -o ConnectTimeout=15 $H"

echo "[chain] watching $CUR (planned 90 cells)"
for i in $(seq 1 300); do
  done_n=$($S "grep -c '^\[done\]' $CUR/batch.log 2>/dev/null || echo 0" 2>/dev/null)
  # the [w] trick stops the ssh wrapper carrying this very pattern from matching itself;
  # head -1 because grep -c prints 0 and then || echo 0 would add a second line
  alive=$($S "ps -eo args | grep -c '[w]ildskills_run.py --serve' || echo 0" 2>/dev/null | head -1)
  done_n=${done_n:-0}; alive=${alive:-0}
  echo "[chain] $(date +%H:%M:%S) done=$done_n/90 serve_procs=$alive"
  if [ "$done_n" -ge 90 ]; then echo "[chain] upstream study complete"; break; fi
  if [ "$alive" -eq 0 ] && [ "$done_n" -gt 0 ]; then
    echo "[chain] WARNING: serve process gone at $done_n/90 -- launching anyway"
    break
  fi
  sleep 60
done

$S "docker rm -f \$(docker ps -aq --filter status=exited) >/dev/null 2>&1; docker network prune -f >/dev/null 2>&1; echo '[chain] swept docker'"

running=$($S "pgrep -fc 'multi25_run.py' 2>/dev/null || echo 0" 2>/dev/null)
if [ "${running:-0}" -gt 0 ]; then
  echo "[chain] skillbench driver already running ($running procs); not launching again"
  exit 0
fi

echo "[chain] launching 225-cell skillbench DeepSeek study (3 workers)"
$S "cd $NEW && nohup $PY -u runner-source/multi25_run.py --workers 3 \
      --arms NoSkill,OriginalSkill,RepairedSkill > batch.log 2>&1 < /dev/null & \
    sleep 8; pgrep -af multi25_run.py | head -2"
echo "[chain] launched"
