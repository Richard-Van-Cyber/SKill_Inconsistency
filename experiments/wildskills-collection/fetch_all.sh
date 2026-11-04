#!/bin/bash
# wildskills-collection/fetch_all.sh — pull every wildskills study off the server, split by model axis.
#
#   bash fetch_all.sh                 # essential files only (skips api/, ~20% of the volume)
#   bash fetch_all.sh --full          # everything, including the raw api/ request logs
#   bash fetch_all.sh --axis deepseek # only one axis
#   bash fetch_all.sh --manifest-only # just the cell manifest + summary (a few hundred KB)
#
# Layout produced (both axes keep every study's own runs/ tree):
#   wildskills-collection/<axis>/<batch>/<study>/runs/<cell>/<task>__<model>/{result.json,benchflow/,cli.stdout.jsonl,…}
set -u
HOST=10.0.0.64
EXP=/home/user/project/experiments
HERE=$(cd "$(dirname "$0")" && pwd)
FULL=0; AXIS="haiku deepseek"; MANIFEST_ONLY=0
for a in "$@"; do
  case "$a" in
    --full) FULL=1;;
    --manifest-only) MANIFEST_ONLY=1;;
    --axis) shift 2>/dev/null;;
    haiku|deepseek) AXIS="$a";;
  esac
done

# axis:batch:study  — keep in sync with experiments/wildskills25-20261001/build_manifest.py
MAP="
haiku:wildskills12:wildskills-20260926
haiku:wildskills12:wildskills2-20260926
haiku:wildskills12:wildskills3-20260926
haiku:wildskills12:wildskills3b-20260926
haiku:wildskills12:wildskills3c-20260926
haiku:wildskills12:wildskills5-20260927
haiku:wildskills12:wildskills5b-20260927
haiku:wildskills12:wildskills6-20260927
haiku:wildskills12:wildskills7-20260927
haiku:wildskills12:wildskills8-20260927
haiku:wildskills12:wildskills9-20260927
haiku:wildskills12:wildskills10-20260927
haiku:wildskills13:wildskills13-20260929
haiku:wildskills13:wildskills13b-20260929
haiku:wildskills13:wildskills13c-20260929
haiku:wildskills13-pilot:wildskills13-pilot-20260929
haiku:wildskills13-placebo:wildskills13-placebo-20260929
haiku:wildskills25:wildskills25-20261001a
haiku:wildskills25:wildskills25-20261001b
haiku:wildskills25:wildskills25-20261001c
haiku:wildskills25-placebo:wildskills25-placebo-20261001
deepseek:wildskills12:wildskills-deepseek-20260927
deepseek:wildskills12:wildskills-deepseek-b2-20260927
deepseek:wildskills12:wildskills-deepseek-smoke
deepseek:wildskills13:wildskills13-deepseek-20260929
deepseek:wildskills25:wildskills25-deepseek-20261001
"

echo "[fetch] manifest + summary"
rsync -a "$HOST:$EXP/wildskills-collection/manifest.csv" "$HERE/" 2>/dev/null
rsync -a "$HOST:$EXP/wildskills-collection/SUMMARY.md"  "$HERE/" 2>/dev/null
ls -la "$HERE/manifest.csv" "$HERE/SUMMARY.md" 2>/dev/null | awk '{print "  ", $9, $5}'
[ "$MANIFEST_ONLY" = "1" ] && exit 0

EXCL=""
if [ "$FULL" = "0" ]; then
  # api/ is the raw request+stream log: ~80% of the bytes, rarely needed for analysis
  EXCL="--exclude api/ --exclude __pycache__"
fi

echo "[fetch] runs (mode: $([ "$FULL" = 1 ] && echo full || echo essential))  axes: $AXIS"
echo "$MAP" | while IFS=: read -r axis batch study; do
  [ -z "${axis:-}" ] && continue
  case " $AXIS " in *" $axis "*) ;; *) continue;; esac
  dest="$HERE/$axis/$batch/$study"
  mkdir -p "$dest"
  rsync -a $EXCL "$HOST:$EXP/$study/runs" "$dest/" 2>/dev/null
  n=$(ls "$dest/runs" 2>/dev/null | wc -l | tr -d ' ')
  printf "  %-9s %-18s %-32s %s cells\n" "$axis" "$batch" "$study" "$n"
done
echo "[fetch] done -> $HERE"
du -sh "$HERE" 2>/dev/null | awk '{print "  total", $1}'
