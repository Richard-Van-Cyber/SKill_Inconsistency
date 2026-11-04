#!/bin/bash
# Pull the gpt-oss:20b wildskills axis back to this Mac.
#
#   experiments/wildskills49-gptoss-20261002/runs/      one dir per cell (result.json + evidence)
#   experiments/wildskills49-gptoss-20261002/reports/    manifest.csv, SUMMARY.md, gptoss-report.md
#
# Safe to run repeatedly (incremental rsync); used both mid-flight and after completion.
set -eu
HOST=user@10.0.0.64
SRC=/home/user/project/experiments/wildskills49-gptoss-20261002
COLL=/home/user/project/experiments/wildskills-gptoss-collection
DST=/workspace/skillEvaluation/experiments/wildskills49-gptoss-20261002

mkdir -p "$DST/runs" "$DST/reports"
# NOTE: macOS ships openrsync/2.6.9; only portable flags are used here (no --info/--ignore-missing-args).
# One recursive sync of the study tree covers runs/, summary.json, execution-status.json, batch.log,
# protocol.json, schedule.json and runner-source; inputs/ and .runtime are large and stay on the server.
echo "[pull] study tree ($(date '+%F %T'))"
rsync -a --stats --exclude 'inputs/' --exclude '.runtime' --exclude '__pycache__' \
      "$HOST:$SRC/" "$DST/" | tail -6
echo "[pull] reports"
rsync -a "$HOST:$COLL/" "$DST/reports/" 2>/dev/null || true
echo "[pull] orchestrator logs"
rsync -a "$HOST:/home/user/project/experiments/wildskills49-gptoss-orchestrator/" \
      "$DST/reports/" 2>/dev/null || true
echo "[pull] local summary"
python3 - "$DST" <<'PYEOF'
import glob, json, os, re, statistics, sys
dst = sys.argv[1]
CANON = re.compile(r"^.+__(NoSkill|OriginalSkill|FixedSkill)__r[0-9]+$")
per, st = {}, {}
for p in glob.glob(os.path.join(dst, "runs", "*", "result.json")):
    cell = p.split("/runs/")[1].split("/")[0]
    if not CANON.match(cell):
        continue
    d = json.load(open(p))
    st[d.get("status")] = st.get(d.get("status"), 0) + 1
    if isinstance(d.get("score"), (int, float)):
        per.setdefault(d.get("arm"), []).append(d["score"])
term = sum(v for k, v in st.items() if k not in ("agent_running", "verifying"))
print(f"  local cells: terminal={term}/441  statuses={st}")
for arm in ("NoSkill", "OriginalSkill", "FixedSkill"):
    xs = per.get(arm, [])
    if xs:
        print(f"  {arm}: n={len(xs)} mean={statistics.mean(xs):.4f}")
PYEOF
