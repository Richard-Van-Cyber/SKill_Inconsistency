#!/bin/bash
# Faithful in-container G0 diagnostic for a wildskills25 task.
#   * creates the sandbox user the harness uses (images do not ship one)
#   * seeds the workspace from the image, snapshots it, runs the oracle AS THAT USER
#   * runs the verifier as root (same as the harness), prints reward + failing CTRF items
# Usage: bash g0_diag2.sh <task> [pristine|fixed]
set -u
REPO=/workspace/skillEvaluation
HOST=10.0.0.64
REMOTE=/home/user/project/g0-wildskills25
T=${1:?task}; M=${2:-pristine}
cd "$REPO" || exit 1
# refresh the server-side copies so we never diagnose stale files
rsync -a "wildskills/dynamic_eval/tasks/$T/oracle/"   "$HOST:$REMOTE/$T-oracle/"   2>/dev/null
rsync -a "wildskills/dynamic_eval/tasks/$T/verifier/" "$HOST:$REMOTE/$T-verifier/" 2>/dev/null
rsync -a "wildskills/dynamic_eval/tasks/$T/environment/skills/" "$HOST:$REMOTE/$T-skills-pristine/" 2>/dev/null
[ -d "wildskills/dynamic_eval/fixed_skills/$T/environment/skills" ] && rsync -a "wildskills/dynamic_eval/fixed_skills/$T/environment/skills/" "$HOST:$REMOTE/$T-skills-fixed/" 2>/dev/null
ssh -o BatchMode=yes "$HOST" bash -s <<EOF
set -u
docker rm -f g0-diag >/dev/null 2>&1
docker run -d --name g0-diag anonymous/$T:g0 sleep infinity >/dev/null 2>&1 || { echo CONTAINER_FAILED; exit 0; }
# sandbox user, exactly like the harness does before the agent phase
docker exec g0-diag bash -c 'id agent >/dev/null 2>&1 || (useradd -m -s /bin/bash agent >/dev/null 2>&1); mkdir -p /logs/verifier /oracle /verifier' >/dev/null 2>&1
docker exec g0-diag bash -c 'rm -rf /tmp/ws-pristine && cp -a /app/workspace /tmp/ws-pristine && chown -R agent:agent /app/workspace /home/agent && chmod -R a+rX /tmp/ws-pristine' >/dev/null 2>&1
docker exec g0-diag bash -c 'rm -rf /app/skills && mkdir -p /app/skills' >/dev/null 2>&1
docker cp $REMOTE/$T-skills-$M/. g0-diag:/app/skills >/dev/null 2>&1
docker cp $REMOTE/$T-oracle/. g0-diag:/oracle >/dev/null 2>&1
docker cp $REMOTE/$T-verifier/. g0-diag:/verifier >/dev/null 2>&1
docker exec g0-diag bash -c 'rm -rf /app/workspace && cp -a /tmp/ws-pristine /app/workspace && chown -R agent:agent /app/workspace && chmod -R u+rwX /app/workspace' >/dev/null 2>&1
docker exec -u agent g0-diag bash -c 'cd /app/workspace && timeout 600 bash /oracle/solve.sh >/tmp/o.log 2>&1; echo ORACLE_RC=\$?'
echo '--- oracle log tail:'
docker exec g0-diag tail -5 /tmp/o.log 2>&1
docker exec g0-diag bash /verifier/test.sh >/dev/null 2>&1
echo "--- reward: \$(docker exec g0-diag cat /logs/verifier/reward.txt 2>/dev/null)"
echo '--- ctrf failures:'
docker exec g0-diag python3 -c "
import json
try:
    d=json.load(open('/logs/verifier/ctrf.json'))
    for t in d['results']['tests']:
        if t['status']!='passed': print('  FAIL', t['name'])
except Exception as e: print('  (no ctrf:', e, ')')
" 2>&1
docker rm -f g0-diag >/dev/null 2>&1
EOF
