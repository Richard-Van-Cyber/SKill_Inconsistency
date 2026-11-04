#!/usr/bin/env bash
# Re-audit the tasks whose previous report was a comprehension collapse
# (total_files > 0 but components == []).
#
# Usage: bash analysis_tools/rerun_failed_audits.sh [PARALLEL_JOBS]
#
# Each task is retried up to 3 times: the original batch failed on transient
# provider hiccups, so a single retry is not enough evidence of a real problem.

set -uo pipefail

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASKS_DIR="$WS/tasks"
AUDIT_DIR="$WS/skill-audit"
CONFIG="$AUDIT_DIR/config.yaml"
JOBS="${1:-3}"
MAX_ATTEMPTS=3

PENDING="$(python3 - "$TASKS_DIR" <<'PY'
import glob, json, os, sys
root = sys.argv[1]
for p in sorted(glob.glob(os.path.join(root, "*", "audit_report.json"))):
    d = json.load(open(p))
    sm = d.get("skill_map_summary") or {}
    if (sm.get("total_files") or 0) > 0 and not (sm.get("components") or []):
        print(os.path.basename(os.path.dirname(p)))
PY
)"
N_PENDING=$(printf '%s\n' "$PENDING" | grep -c . || true)

echo "Re-auditing $N_PENDING tasks with $JOBS parallel jobs, up to $MAX_ATTEMPTS attempts each"
echo "=============================================="

audit_one() {
    local task="$1"
    local skill_dir="$TASKS_DIR/$task/environment/skills"
    local report="$TASKS_DIR/$task/audit_report.json"
    local log="$TASKS_DIR/$task/audit.log"
    [ -d "$skill_dir" ] || { echo "SKIP $task (no skills dir)"; return; }

    local attempt=1
    while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
        if python3 "$AUDIT_DIR/main.py" \
                --skill-dir "$skill_dir" \
                --config "$CONFIG" \
                --output "$report" >"$log" 2>&1; then
            local n
            n=$(python3 -c "import json,sys;d=json.load(open('$report'));print(len((d.get('skill_map_summary') or {}).get('components') or []))")
            if [ "$n" -gt 0 ]; then
                echo "OK  $task (attempt $attempt, $n components)"
                return
            fi
            echo "BAD $task (attempt $attempt: 0 components)"
        else
            echo "ERR $task (attempt $attempt, see $task/audit.log)"
        fi
        attempt=$((attempt + 1))
        sleep 5
    done
    echo "FAIL $task after $MAX_ATTEMPTS attempts"
}

export -f audit_one
export TASKS_DIR AUDIT_DIR CONFIG MAX_ATTEMPTS

printf '%s\n' "$PENDING" | xargs -P "$JOBS" -I{} bash -c 'audit_one "$@"' _ {}

echo "=============================================="
python3 - "$TASKS_DIR" <<'PY'
import glob, json, os, sys
root = sys.argv[1]
ok = bad = 0
for p in sorted(glob.glob(os.path.join(root, "*", "audit_report.json"))):
    d = json.load(open(p))
    sm = d.get("skill_map_summary") or {}
    if (sm.get("total_files") or 0) > 0 and not (sm.get("components") or []):
        bad += 1
    else:
        ok += 1
print(f"Reports with a usable skill map: {ok}; still collapsed: {bad}")
PY
