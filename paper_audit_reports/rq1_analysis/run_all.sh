#!/usr/bin/env bash
# Rebuild every RQ1 artefact from the audit reports.
#
#   cd paper_audit_reports/rq1_analysis
#   bash run_all.sh
#
# Inputs : ../skillbench_audit/*/audit_report.json   (SkillBench)
#          ../wildskills_audit/*/audit_report.json   (GitHub skills)
#          ../skill_category_distribution.csv        (domain labels)
#          ../../tasks/*/environment/skills, ../../wildskills/{skills,scripts_skills}
#
# Outputs: outputs/*.csv, outputs/*.tex, outputs/rq1_stats.json, figures/*.pdf|png
set -euo pipefail
cd "$(dirname "$0")"

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mplcache}"   # writable matplotlib cache
PY="${PY:-python3}"

echo "== 1/5 build dataset =========================================="
$PY build_dataset.py

echo "== 2/5 prevalence and density (RQ1-A) ========================="
$PY analyze_prevalence.py

echo "== 3/5 types (RQ1-B) =========================================="
$PY analyze_types.py

echo "== 4/5 co-occurrence (RQ1-C) =================================="
$PY analyze_cooccurrence.py

echo "== 5/5 figures ================================================"
$PY make_figures.py

echo
echo "done. tables in outputs/, figures in figures/"
