#!/bin/bash
# wildskills25 — in-container G0 sweep (oracle 1.0 in the REAL image, 3 repeats).
#
# For every built task:
#   1. rsync environment/ to the server and `docker build` the task image (validates the Dockerfile)
#   2. start a container, copy the task's oracle/ and verifier/ in
#   3. run oracle/solve.sh in /app/workspace, then /verifier/test.sh, read reward.txt  (x3)
#   4. also run the verifier on a pristine copy of the workspace (expected < 1.0)
#
# This complements BUILD-GUIDE's docker-free local gate: it exercises the real image, real paths and
# real dependency set, so a missing apt/pip package or a path assumption fails here instead of
# silently burning 9 experiment cells.
#
# Usage: bash g0_sweep.sh [task ...]        (default: every built task)
set -u
REPO=/workspace/skillEvaluation
HOST=10.0.0.64
REMOTE=/home/user/project/g0-wildskills25
REPEATS=3
cd "$REPO" || exit 1

if [ "$#" -gt 0 ]; then TASKS="$*"; else
  TASKS=$(python3 - <<'PY'
import json
from pathlib import Path
reg = json.load(open('experiments/wildskills25-20261001/tasks.json'))['tasks']
out = []
for t in reg:
    n = t['task']
    if str(t.get('status', '')).startswith(('rejected', 'dropped')):
        continue
    if (Path('wildskills/dynamic_eval/tasks') / n / 'task.md').is_file():
        out.append(n)
print(' '.join(out))
PY
)
fi
echo "[g0] tasks: $TASKS"

ssh -o BatchMode=yes "$HOST" "mkdir -p $REMOTE" || exit 1
for t in $TASKS; do
  D="wildskills/dynamic_eval/tasks/$t"
  IMG="anonymous/$t:g0"
  echo "=== $t"
  rsync -a --delete "$D/environment/" "$HOST:$REMOTE/$t/" 2>/dev/null
  if ! ssh -o BatchMode=yes "$HOST" "cd $REMOTE/$t && docker build -q -t $IMG . >/dev/null 2>$REMOTE/$t.build.err"; then
    echo "  BUILD FAILED: $(ssh -o BatchMode=yes "$HOST" "tail -3 $REMOTE/$t.build.err" | tr '\n' ' ')"
    continue
  fi
  ssh -o BatchMode=yes "$HOST" "docker rm -f g0-$t >/dev/null 2>&1; docker run -d --name g0-$t $IMG sleep infinity >/dev/null" || { echo "  RUN FAILED"; continue; }
  # copy oracle + verifier (and, when present, the FixedSkill overlay as the /app/skills mount)
  rsync -a "$D/oracle/" "$HOST:$REMOTE/$t-oracle/" 2>/dev/null
  rsync -a "$D/verifier/" "$HOST:$REMOTE/$t-verifier/" 2>/dev/null
  # Oracles come in two flavours: patch-style ones start from the PRISTINE tree, derive-style ones
  # read the REPAIRED overlay and refuse anything else.  Mount both and require 1.0 in at least one.
  rsync -a "$D/environment/skills/" "$HOST:$REMOTE/$t-skills-pristine/" 2>/dev/null
  if [ -d "wildskills/dynamic_eval/fixed_skills/$t/environment/skills" ]; then
    rsync -a "wildskills/dynamic_eval/fixed_skills/$t/environment/skills/" "$HOST:$REMOTE/$t-skills-fixed/" 2>/dev/null
    MOUNTS="pristine fixed"
  else
    MOUNTS="pristine"
  fi
  ssh -o BatchMode=yes "$HOST" "
    docker exec g0-$t bash -c 'id agent >/dev/null 2>&1 || useradd -m -s /bin/bash agent; mkdir -p /logs/verifier /oracle /verifier; rm -rf /tmp/ws-pristine && cp -a /app/workspace /tmp/ws-pristine && chmod -R a+rX /tmp/ws-pristine' >/dev/null 2>&1
    docker cp $REMOTE/$t-oracle/. g0-$t:/oracle >/dev/null 2>&1
    docker cp $REMOTE/$t-verifier/. g0-$t:/verifier >/dev/null 2>&1
   for M in $MOUNTS; do
    echo \"  [mount=\$M]\"
    docker exec g0-$t bash -c 'rm -rf /app/skills && mkdir -p /app/skills' >/dev/null 2>&1
    docker cp $REMOTE/$t-skills-\$M/. g0-$t:/app/skills >/dev/null 2>&1
    for i in \$(seq 1 $REPEATS); do
      docker exec g0-$t bash -c 'rm -rf /app/workspace && cp -a /tmp/ws-pristine /app/workspace && chown -R agent:agent /app/workspace && rm -f /logs/verifier/reward.txt' >/dev/null 2>&1
      docker exec -u agent g0-$t bash -c 'cd /app/workspace && timeout 900 bash /oracle/solve.sh >/tmp/oracle.log 2>&1; echo oracle_rc=\$?' | tr -d '\n'
      docker exec g0-$t bash /verifier/test.sh >/tmp/verifier.log 2>&1
      R=\$(docker exec g0-$t cat /logs/verifier/reward.txt 2>/dev/null | tr -d '\n')
      echo \"    run\$i reward=\$R\"
    done
   done
  " 2>&1 | sed 's/^/  /'
  ssh -o BatchMode=yes "$HOST" "
    docker exec g0-$t bash -c 'rm -rf /app/workspace && cp -a /tmp/ws-pristine /app/workspace && rm -f /logs/verifier/reward.txt' >/dev/null 2>&1
    docker exec g0-$t bash /verifier/test.sh >/dev/null 2>&1
    echo \"  pristine reward=\$(docker exec g0-$t cat /logs/verifier/reward.txt 2>/dev/null | tr -d \"\\n\")\"
  " 2>&1 | sed 's/^/  /'
  ssh -o BatchMode=yes "$HOST" "docker rm -f g0-$t >/dev/null 2>&1"
done
echo "[g0] done"
