#!/usr/bin/env bash
# P11 feasibility gate: can the SHIPPED task be passed at all?
#
# Runs the task's own oracle, then its own verifier, inside the real task image.
# No agent, no API calls. A task that cannot reach reward 1.0 here cannot be used
# for an adversarial experiment: the inconsistency would never be the binding
# constraint (this is exactly how the adaptive-cruise-control 1.95 m defect was
# found -- its `min_d >= 5` check is unsatisfiable on the shipped data).
#
# Usage (on the server):
#   bash feasibility_gate.sh <task> [<task> ...]
# Writes /tmp/feasibility/<task>.log and prints a one-line verdict per task.

set -uo pipefail
REPO=/home/user/project
OUT=/tmp/feasibility
mkdir -p "$OUT"

for task in "$@"; do
  log="$OUT/$task.log"
  taskdir="$REPO/inputs/selected_tasks/$task"
  # fall back to any study that has this task package
  if [ ! -d "$taskdir" ]; then
    taskdir=$(ls -d "$REPO"/adv_stage/"$task" 2>/dev/null | head -1)
  fi
  if [ -z "${taskdir:-}" ] || [ ! -d "$taskdir" ]; then
    taskdir=$(ls -d "$REPO"/experiments/*/inputs/selected_tasks/"$task" 2>/dev/null | head -1)
  fi
  if [ -z "${taskdir:-}" ] || [ ! -d "$taskdir" ]; then
    echo "SKIP  $task (no task package on the server)"
    continue
  fi
  tag=$(python3 - "$taskdir" <<'PY'
import hashlib, sys
from pathlib import Path
task = Path(sys.argv[1]); d = hashlib.sha256()
for p in sorted((task / 'environment').rglob('*')):
    if p.is_file() and p.name != '.DS_Store':
        d.update(str(p.relative_to(task)).encode()); d.update(p.read_bytes())
print('anonymous/' + task.name + ':' + d.hexdigest()[:12])
PY
)
  if ! docker image inspect "$tag" >/dev/null 2>&1; then
    echo "BUILD $task ($tag)"
    if ! docker build -t "$tag" "$taskdir/environment" >"$log.build" 2>&1; then
      echo "FAIL  $task (image build failed; see $log.build)"
      continue
    fi
  fi

  {
    echo "=== task: $task  image: $tag"
    echo "=== oracle ==="
    # Inject the cached uv/uvx exactly as the real runner does
    # (verifier_dependencies.py copies them to /root/.local/bin). Without this the gate
    # reports a false FAIL for every task whose test.sh bootstraps uv from the network:
    # this sandbox cannot reach github.com, so `curl ... | sh` dies and the verifier's
    # `uvx` is missing -> pytest never runs -> reward 0. That is a gate artefact, not a
    # task defect (e.g. citation-check grades 1.0 in the real run).
    UV_CACHE="$REPO/experiments/directed-repair-20260922/.runtime/verifier-cache"
    docker run --rm \
      -v "$taskdir/oracle:/oracle:ro" \
      -v "$taskdir/verifier:/verifier:ro" \
      -v "$UV_CACHE:/uvcache:ro" \
      "$tag" bash -c '
        mkdir -p /logs/verifier /root/.local/bin
        if [ -x /uvcache/uv ] && [ -x /uvcache/uvx ]; then
          cp /uvcache/uv /uvcache/uvx /root/.local/bin/ && chmod 755 /root/.local/bin/uv /root/.local/bin/uvx
          echo "UV_INJECTED=yes"
        else
          echo "UV_INJECTED=no"
        fi
        # test.sh does `source $HOME/.local/bin/env`; provide it so the bootstrap line
        # failing does not abort the rest of the script.
        [ -f /root/.local/bin/env ] || printf "export PATH=/root/.local/bin:$PATH\n" > /root/.local/bin/env
        if [ -f /oracle/solve.sh ]; then bash /oracle/solve.sh; echo "ORACLE_EXIT=$?"; else echo "NO_ORACLE"; fi
        echo "=== verifier ==="
        if [ -f /verifier/test.sh ]; then bash /verifier/test.sh; echo "VERIFIER_EXIT=$?"; else echo "NO_VERIFIER"; fi
        echo "=== reward ==="
        cat /logs/verifier/reward.txt 2>/dev/null || echo "(no reward.txt)"
      ' 2>&1
  } >"$log"

  reward=$(grep -A1 '=== reward ===' "$log" | tail -1 | tr -d '[:space:]')
  oracle_exit=$(grep -o 'ORACLE_EXIT=[0-9]*' "$log" | tail -1 | cut -d= -f2)
  # reward.txt is written by each task's own test.sh, so its spelling varies:
  # `1`, `1.0` and `1.000` all mean a full pass. Compare numerically, not as strings
  # (a literal `= "1.0"` test reported civ6-adjacency-optimizer as FAIL at reward 1.000).
  reward_ok=$(awk -v r="$reward" 'BEGIN{ exit !(r+0 >= 1) }' 2>/dev/null && echo yes || echo no)
  if [ "$reward_ok" = "yes" ]; then
    echo "PASS  $task  (oracle_exit=${oracle_exit:-?} reward=$reward)"
  else
    echo "FAIL  $task  (oracle_exit=${oracle_exit:-?} reward=${reward:-none})  see $log"
  fi
done
