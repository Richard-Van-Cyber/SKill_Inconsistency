#!/usr/bin/env bash
# Build the task images the multi25 study needs, on the server.
# Usage: bash build_images.sh <tagfile>
set -uo pipefail
REPO=/home/user/project
STUDY=$REPO/experiments/multi25-20260925
TAGS=${1:-/tmp/tags25.txt}
LOG=/tmp/build25.log
: > "$LOG"

built=0; skipped=0; failed=0
while read -r tag; do
  [ -z "$tag" ] && continue
  task=$(printf '%s' "$tag" | sed 's|^anonymous/||; s|:.*||')
  if docker image inspect "$tag" >/dev/null 2>&1; then
    echo "SKIP $task (present)" | tee -a "$LOG"; skipped=$((skipped+1)); continue
  fi
  env_dir="$STUDY/inputs/selected_tasks/$task/environment"
  if [ ! -d "$env_dir" ]; then
    echo "FAIL $task (no environment dir at $env_dir)" | tee -a "$LOG"; failed=$((failed+1)); continue
  fi
  echo "BUILD $task -> $tag" | tee -a "$LOG"
  if docker build -t "$tag" "$env_dir" >>"$LOG" 2>&1; then
    echo "OK   $task" | tee -a "$LOG"; built=$((built+1))
  else
    echo "FAIL $task (see $LOG)" | tee -a "$LOG"; failed=$((failed+1))
  fi
done < "$TAGS"
echo "==== built=$built skipped=$skipped failed=$failed ====" | tee -a "$LOG"
