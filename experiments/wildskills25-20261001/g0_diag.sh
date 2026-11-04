#!/bin/bash
# Diagnose a wildskills25 task in-container: run the oracle (given mount), run the verifier,
# and print reward + the failing checks.  Usage: bash g0_diag.sh <task> [pristine|fixed]
set -u
REPO=/workspace/skillEvaluation
HOST=10.0.0.64
REMOTE=/home/user/project/g0-wildskills25
T=${1:?task}; M=${2:-pristine}
cd "$REPO" || exit 1
OUT=$(ssh -o BatchMode=yes "$HOST" bash -s <<EOF
set -u
docker rm -f g0-diag >/dev/null 2>&1
docker run -d --name g0-diag anonymous/$T:g0 sleep infinity >/dev/null 2>&1 || { echo "CONTAINER_FAILED"; exit 0; }
docker exec g0-diag bash -c 'mkdir -p /logs/verifier /oracle /verifier && rm -rf /tmp/ws-pristine && cp -a /app/workspace /tmp/ws-pristine' >/dev/null 2>&1
docker exec g0-diag bash -c 'rm -rf /app/skills && mkdir -p /app/skills' >/dev/null 2>&1
docker cp $REMOTE/$T-skills-$M/. g0-diag:/app/skills >/dev/null 2>&1
docker cp $REMOTE/$T-oracle/. g0-diag:/oracle >/dev/null 2>&1
docker cp $REMOTE/$T-verifier/. g0-diag:/verifier >/dev/null 2>&1
docker exec g0-diag bash -c 'rm -rf /app/workspace && cp -a /tmp/ws-pristine /app/workspace && cd /app/workspace && timeout 600 bash /oracle/solve.sh >/tmp/o.log 2>&1; echo "ORACLE_RC=\$?"'
echo "--- oracle log tail:"
docker exec g0-diag tail -6 /tmp/o.log 2>&1
docker exec g0-diag bash /verifier/test.sh >/dev/null 2>&1
echo "--- verifier:"
docker exec g0-diag cat /logs/verifier/reward.txt 2>/dev/null
docker exec g0-diag cat /logs/verifier/verifier-detail.json 2>/dev/null
docker rm -f g0-diag >/dev/null 2>&1
EOF
)
echo "$OUT" | grep -E "ORACLE_RC|CONTAINER_FAILED" || true
echo "$OUT" | sed -n '/--- oracle log tail:/,/--- verifier:/p' | head -10
REWARD=$(echo "$OUT" | sed -n '/--- verifier:/{n;p;}' | tr -d '\n')
echo "reward=$REWARD"
echo "$OUT" | python3 -c "
import sys, json
txt = sys.stdin.read()
i = txt.find('{\"checks\"')
if i < 0:
    print('  (no verifier-detail.json)'); raise SystemExit
try:
    d = json.loads(txt[i:])
except Exception as e:
    print('  (detail parse failed:', e, ')'); raise SystemExit
bad = [c for c in d.get('checks', []) if not c.get('passed')]
print(f'  failing {len(bad)}/{len(d.get(\"checks\", []))}:')
for c in bad[:6]:
    print('   -', c['name'], '::', str(c.get('detail'))[:150])
"