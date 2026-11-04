#!/bin/bash
# wildskills25 — post-run verification & recovery (client side, run when the network is back).
#
#   bash postrun_check.sh                 # status only
#   bash postrun_check.sh --recover       # re-run every non-graded cell (explicit --cells)
#   bash postrun_check.sh --sync          # rsync runs/ + dataset back home
#   bash postrun_check.sh --analyze       # run the local analysis pipeline
set -u
REPO=/workspace/skillEvaluation
HOST=10.0.0.64
EXP=/home/user/project/experiments
PY=/home/user/project/.venv-benchflow/bin/python
STUDIES="wildskills25-20261001a wildskills25-20261001b wildskills25-20261001c wildskills25-placebo-20261001"
RECOVER=0; SYNC=0; ANALYZE=0
for a in "$@"; do case "$a" in --recover) RECOVER=1;; --sync) SYNC=1;; --analyze) ANALYZE=1;; esac; done

ssh -o BatchMode=yes -o ConnectTimeout=15 -n "$HOST" true 2>/dev/null || { echo "server unreachable"; exit 2; }

# helper on the server: status table, or the comma-separated failed cell ids for one study
ssh -o BatchMode=yes -n "$HOST" "cat > $EXP/wildskills25-status.py" <<'PY'
import glob, json, sys
EXP = '/home/user/project/experiments'
PLANNED = {'wildskills25-20261001a': 72, 'wildskills25-20261001b': 72,
           'wildskills25-20261001c': 63, 'wildskills25-placebo-20261001': 72}

def scan(study):
    graded, other, failed = 0, {}, []
    for p in glob.glob(f'{EXP}/{study}/runs/*/*/result.json'):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        st = d.get('status') or 'unknown'
        if st == 'graded':
            graded += 1
        else:
            other[st] = other.get(st, 0) + 1
            failed.append(p.split('/runs/')[1].split('/')[0])
    return graded, other, sorted(failed)

if len(sys.argv) > 2 and sys.argv[1] == '--failed':
    print(','.join(scan(sys.argv[2])[2]))
else:
    for s in sorted(PLANNED):
        g, o, f = scan(s)
        print(f'{s}  planned={PLANNED[s]} graded={g} other={o or "{}"}')
        for cell in f:
            print(f'    FAILED {cell}')
PY

echo "=== state"
ssh -o BatchMode=yes -n "$HOST" "L=$EXP/wildskills25-orchestrator; tail -3 \$L/orchestrator.log 2>/dev/null; \
  echo DONE=\$([ -f \$L/DONE ] && echo yes || echo no); tail -2 \$L/analyze.log 2>/dev/null; \
  echo containers=\$(docker ps --format '{{.Names}}' | grep -c '^project-ws-') drivers=\$(ps -eo cmd | grep -c '[w]ildskills_run.py --serve')"

echo; echo "=== counts"
ssh -o BatchMode=yes -n "$HOST" "$PY $EXP/wildskills25-status.py"

if [ "$RECOVER" = "1" ]; then
  echo; echo "=== recovering failed cells"
  for s in $STUDIES; do
    CELLS=$(ssh -o BatchMode=yes -n "$HOST" "$PY $EXP/wildskills25-status.py --failed $s" 2>/dev/null)
    if [ -z "$CELLS" ]; then echo "  $s: nothing to recover"; continue; fi
    N=$(echo "$CELLS" | tr ',' '\n' | wc -l | tr -d ' ')
    echo "  $s: re-running $N cell(s)"
    ssh -o BatchMode=yes -n "$HOST" "cd /home/user/project && WS_STUDY_NAME=$s WS_REPEATS=3 \
      setsid nohup $PY -u $EXP/$s/runner-source/wildskills_run.py --serve --workers 2 --cells '$CELLS' \
      >> $EXP/$s/batch.log 2>&1 < /dev/null &"
    sleep 3
  done
fi

if [ "$SYNC" = "1" ]; then
  echo; echo "=== syncing"
  for s in $STUDIES; do
    rsync -a --exclude '__pycache__' --exclude 'api' "$HOST:$EXP/$s/runs" "$REPO/experiments/$s/" 2>/dev/null
    printf "  %-32s %s cells\n" "$s" "$(ls "$REPO/experiments/$s/runs" 2>/dev/null | wc -l | tr -d ' ')"
  done
  rsync -a "$HOST:$EXP/wildskills25-dataset/" "$REPO/experiments/wildskills25-dataset/" 2>/dev/null
  ls "$REPO/experiments/wildskills25-dataset/" 2>/dev/null | tr '\n' ' '; echo
fi

if [ "$ANALYZE" = "1" ]; then
  echo; echo "=== local analysis"
  S="wildskills25-20261001a,wildskills25-20261001b,wildskills25-20261001c"
  cd "$REPO" || exit 1
  python3 experiments/wildskills25-20261001/analyze_mechanism.py --studies "$S" 2>&1 | tail -3
  python3 experiments/wildskills25-20261001/analyze_checks.py    --studies "$S" 2>&1 | tail -3
  python3 experiments/wildskills25-20261001/consolidate13.py     --studies "$S" \
      --placebo-study wildskills25-placebo-20261001 2>&1 | tail -3
fi
