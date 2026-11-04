#!/usr/bin/env bash
# Rebuild every derived artifact from the current tasks/*/audit_report.json.
#
# Order matters: exposure -> ranking -> impact report -> forensics -> causal report.
# Run from the workspace root:  bash analysis_tools/refresh_all.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== 1/5 parse baseline runs"
python3 analysis_tools/parse_baseline_runs.py

echo "== 2/5 exposure scan (findings x runs)"
python3 analysis_tools/exposure_scan_baseline.py

echo "== 3/5 impact ranking (87 tasks)"
python3 analysis_tools/impact_ranking.py

echo "== 4/5 impact report"
python3 analysis_tools/make_impact_report.py

echo "== 5/5 trace forensics + causal verdicts"
python3 analysis_tools/trace_forensics.py
python3 analysis_tools/trace_causal_report.py
python3 analysis_tools/make_trace_report.py

echo
echo "done. artifacts:"
ls -la skill_inconsistency_impact_top30.md skill_inconsistency_impact_ranking.csv \
       skill_trace_causal_audit.md skill_trace_causal_audit.csv
