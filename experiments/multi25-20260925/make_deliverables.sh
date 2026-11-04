#!/usr/bin/env bash
# One command that produces every paper-facing artefact from the current run state.
#
#   1. sync runs back from the server (trajectories included)
#   2. consolidate 25 tasks x 3 arms into dataset/ (cells.csv, cells.jsonl, summary.md, manifest.json)
#   3. build the mechanism table (doc-induced defect counts per arm)
#   4. run forensics over our own OriginalSkill traces
#   5. report completeness against the 225-cell plan
#
# Safe to re-run at any time; it always reflects whatever data exists right now.
#
#   bash experiments/multi25-20260925/make_deliverables.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STUDY="$REPO/experiments/multi25-20260925"
HOST=user@10.0.0.64
RS="ssh -o BatchMode=yes -o ConnectTimeout=20 $HOST"
OUT="$STUDY/dataset"

echo "== 1. sync runs from $HOST (trajectories + result.json, skipping bulk artefacts)"
# --delete matters: cells are removed on the server when they are re-queued (a retriable
# infrastructure failure gets its directory deleted so the driver re-runs it). Without
# --delete the local mirror keeps those dead cells and the dataset would report stale
# failures that no longer exist. The server is authoritative.
rsync -a --delete --exclude 'agent-artifacts.tgz' --exclude 'native-session.tgz' --exclude 'api/' \
      -e "ssh -o BatchMode=yes -o ConnectTimeout=20" \
      "$HOST:~/anonymous/experiments/multi25-20260925/runs/" "$STUDY/runs/" 2>/dev/null || true
# The two baseline studies for the original 10 tasks also live on the server. They must be
# synced too: the dataset reads all three studies, and a stale local copy silently reports
# old statuses (e.g. a verifier_error that has since been retried and graded).
for d in experiments/drs-v2-20260925; do
  rsync -a --delete --exclude 'agent-artifacts.tgz' --exclude 'native-session.tgz' --exclude 'api/' \
        -e "ssh -o BatchMode=yes -o ConnectTimeout=20" \
        "$HOST:~/anonymous/$d/runs/" "$REPO/$d/runs/" 2>/dev/null || echo "  WARN: could not sync $d"
done
[ -d "$REPO/haiku45-threeway-20260917/runs" ] || echo "  WARN: haiku45 runs missing"
# haiku45 is the frozen 2026-09-17 study; its runs are archived locally and are not re-run.

echo
echo "== 2. consolidate -> $OUT"
python3 "$REPO/analysis_tools/consolidate25.py" --out "$OUT"

echo
echo "== 2b. section 4 headline (effectiveness + efficiency) -> dataset/section4.md"
python3 "$REPO/analysis_tools/section4.py" --out "$OUT/section4.md"

echo
echo "== 3. mechanism table"
python3 "$REPO/analysis_tools/mechanism25.py" \
        --out "$STUDY/analysis/mechanism-table.md" >/dev/null && echo "  wrote analysis/mechanism-table.md"

echo
echo "== 4. forensics over our own OriginalSkill traces"
python3 "$REPO/analysis_tools/multi25_forensics.py" --study "experiments/multi25-20260925" \
        --arm OriginalSkill --out "$STUDY/analysis/forensics-new15.json" \
        | head -30

echo
echo "== 5. completeness"
python3 - "$OUT/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"  cells {m['cells']} / planned {m['planned']}")
for a, n in m['per_arm'].items():
    print(f"    {a:16} {n}/75" if m['planned'] == 225 else f"    {a:16} {n}")
inc = [t for t, n in m['per_task'].items() if n < 9]
print(f"  incomplete tasks ({len(inc)}): {', '.join(inc) if inc else 'none'}")
PY

echo
echo "done. artefacts:"
ls -1 "$OUT"
