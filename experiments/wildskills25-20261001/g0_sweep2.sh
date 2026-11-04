#!/bin/bash
# wildskills25 — in-container G0 sweep, v2.
#
# v1 ran 3 repeats inside ONE container; state outside /app/workspace (caches, /tmp, gateway dirs)
# survived between repeats, so a task could score 1.0 then 0.67.  Real cells get a fresh container,
# so v2 starts a NEW container per repeat.  For each task it:
#   1. rsyncs environment/ to the server and builds anonymous/<task>:g0   (validates the Dockerfile)
#   2. for each mount in {pristine, fixed} and each repeat: fresh container -> create the sandbox
#      user (images ship none) -> mount skills at /app/skills -> run oracle/solve.sh AS the sandbox
#      user -> run /verifier/test.sh as root -> read reward.txt
#   3. one extra fresh container with no oracle run, to confirm the empty workspace scores 0.0
#
# Usage: bash g0_sweep2.sh [task ...]      (default: every built task)
set -u
REPO=/workspace/skillEvaluation
HOST=10.0.0.64
REMOTE=/home/user/project/g0-wildskills25
REPEATS=${G0_REPEATS:-3}
cd "$REPO" || exit 1

if [ "$#" -gt 0 ]; then TASKS="$*"; else
  TASKS=$(python3 - <<'PY'
import json
from pathlib import Path
reg = json.load(open('experiments/wildskills25-20261001/tasks.json'))['tasks']
print(' '.join(t['task'] for t in reg
               if not str(t.get('status', '')).startswith(('rejected', 'dropped'))
               and (Path('wildskills/dynamic_eval/tasks') / t['task'] / 'task.md').is_file()))
PY
)
fi

ssh -o BatchMode=yes "$HOST" "mkdir -p $REMOTE" || exit 1
for t in $TASKS; do
  D="wildskills/dynamic_eval/tasks/$t"
  IMG="anonymous/$t:g0"
  echo "=== $t"
  rsync -a --delete "$D/environment/" "$HOST:$REMOTE/$t/" 2>/dev/null
  if ! ssh -o BatchMode=yes "$HOST" "cd $REMOTE/$t && docker build -q -t $IMG . >/dev/null 2>$REMOTE/$t.build.err"; then
    echo "  BUILD FAILED: $(ssh -o BatchMode=yes "$HOST" "tail -2 $REMOTE/$t.build.err" | tr '\n' ' ' | cut -c1-160)"
    continue
  fi
  rsync -a "$D/oracle/"   "$HOST:$REMOTE/$t-oracle/"   2>/dev/null
  rsync -a "$D/verifier/" "$HOST:$REMOTE/$t-verifier/" 2>/dev/null
  rsync -a "$D/environment/skills/" "$HOST:$REMOTE/$t-skills-pristine/" 2>/dev/null
  MOUNTS=pristine
  if [ -d "wildskills/dynamic_eval/fixed_skills/$t/environment/skills" ]; then
    rsync -a "wildskills/dynamic_eval/fixed_skills/$t/environment/skills/" "$HOST:$REMOTE/$t-skills-fixed/" 2>/dev/null
    MOUNTS="pristine fixed"
  fi
  for M in $MOUNTS; do
    for r in $(seq 1 "$REPEATS"); do
      R=$(ssh -o BatchMode=yes "$HOST" bash -s <<EOF
C=g0-$t-$M-$r
docker rm -f \$C >/dev/null 2>&1
docker run -d --name \$C $IMG sleep infinity >/dev/null 2>&1 || { echo RUN_FAILED; exit 0; }
docker exec \$C bash -c 'id agent >/dev/null 2>&1 || useradd -m -s /bin/bash agent; mkdir -p /logs/verifier /oracle /verifier; rm -rf /tmp/ws-pristine && cp -a /app/workspace /tmp/ws-pristine && chmod -R a+rX /tmp/ws-pristine' >/dev/null 2>&1
docker exec \$C bash -c 'rm -rf /app/skills && mkdir -p /app/skills' >/dev/null 2>&1
docker cp $REMOTE/$t-skills-$M/. \$C:/app/skills >/dev/null 2>&1
docker cp $REMOTE/$t-oracle/. \$C:/oracle >/dev/null 2>&1
docker cp $REMOTE/$t-verifier/. \$C:/verifier >/dev/null 2>&1
docker exec \$C bash -c 'rm -rf /app/workspace && cp -a /tmp/ws-pristine /app/workspace && chown -R agent:agent /app/workspace' >/dev/null 2>&1
docker exec -u agent \$C bash -c 'cd /app/workspace && timeout 900 bash /oracle/solve.sh >/tmp/o.log 2>&1; echo RC=\$?' | tr -d '\n'
docker exec \$C bash /verifier/test.sh >/dev/null 2>&1
echo " reward=\$(docker exec \$C cat /logs/verifier/reward.txt 2>/dev/null | tr -d '\n')"
docker rm -f \$C >/dev/null 2>&1
EOF
)
      echo "  [mount=$M r$r] $R"
    done
  done
  # empty-workspace control in a fresh container
  R=$(ssh -o BatchMode=yes "$HOST" bash -s <<EOF
C=g0-$t-empty
docker rm -f \$C >/dev/null 2>&1
docker run -d --name \$C $IMG sleep infinity >/dev/null 2>&1 || { echo RUN_FAILED; exit 0; }
docker exec \$C bash -c 'mkdir -p /logs/verifier /verifier' >/dev/null 2>&1
docker cp $REMOTE/$t-verifier/. \$C:/verifier >/dev/null 2>&1
docker exec \$C bash /verifier/test.sh >/dev/null 2>&1
echo " reward=\$(docker exec \$C cat /logs/verifier/reward.txt 2>/dev/null | tr -d '\n')"
docker rm -f \$C >/dev/null 2>&1
EOF
)
  echo "  [empty workspace]$R"
done
echo "[g0] done"
