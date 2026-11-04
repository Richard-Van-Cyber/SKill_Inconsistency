#!/bin/bash
# Retry the cells that failed for AGENT-level reasons (status agent_error), after the main
# sweep has written its DONE marker.
#
# `environment_error` cells are deliberately NOT retried: for `blog-search` the task image ships
# the skill, so the NoSkill arm can never pass the isolation probe — retrying would just fail
# again (the paper drops those cells from the NoSkill arm).
#
# Runs with --workers 1 so the retry cannot collide with the main batch and so the single cell
# gets the whole model (no batching penalty).
set -u
ROOT=/home/user/project
EXP=$ROOT/experiments
PY=$ROOT/.venv-benchflow/bin/python
STUDY=wildskills49-gptoss-20261002
LOG=$EXP/wildskills49-gptoss-orchestrator
MARK=$LOG/RETRY-DONE

for i in $(seq 1 180); do          # wait up to 3 h for the main sweep to finish
  [ -f "$LOG/DONE" ] && break
  sleep 60
done
[ -f "$LOG/DONE" ] || { echo "main sweep never reported DONE; not retrying"; exit 2; }

CELLS=$("$PY" - "$EXP/$STUDY" <<'PYEOF'
import glob, json, re, sys
study = sys.argv[1]
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
out = []
for p in glob.glob(study + "/runs/*/result.json"):
    cell = p.split("/runs/")[1].split("/")[0]
    if not CANON.match(cell):
        continue
    d = json.load(open(p))
    if d.get("status") == "agent_error":
        out.append(cell)
print(",".join(out))
PYEOF
)

if [ -z "$CELLS" ]; then
  echo "no agent-level failures to retry"
  date > "$MARK"
  exit 0
fi

# never run two drivers at once: concurrent drivers sweep each other's docker networks
while pgrep -f "^$PY -u .*runner-source/wildskills_run\.py --serve" >/dev/null 2>&1; do
  sleep 30
done

echo "retrying agent_error cells: $CELLS"
(
  cd "$ROOT" && WS_STUDY_NAME="$STUDY" WS_TASKS="$(cat "$EXP/$STUDY/WS_TASKS.txt")" WS_REPEATS=3 \
    WS_MODEL=gpt-oss-20b setsid nohup "$PY" -u "$EXP/$STUDY/runner-source/wildskills_run.py" \
    --serve --workers 1 --cells "$CELLS" >> "$EXP/$STUDY/retry.log" 2>&1 < /dev/null &
)
sleep 20

# wait for the retry driver to exit, then check whether the cells are now graded
while pgrep -f "^$PY -u .*runner-source/wildskills_run\.py --serve" >/dev/null 2>&1; do
  sleep 60
done

"$PY" - "$EXP/$STUDY" "$CELLS" <<'PYEOF'
import glob, json, re, sys
study, cells = sys.argv[1], set(sys.argv[2].split(","))
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
for p in glob.glob(study + "/runs/*/result.json"):
    cell = p.split("/runs/")[1].split("/")[0]
    if cell in cells:
        d = json.load(open(p))
        print("  retry result: %s -> %s score=%s" % (cell, d.get("status"), d.get("score")))
PYEOF
date > "$MARK"
echo "RETRY DONE"
