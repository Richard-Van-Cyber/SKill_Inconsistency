#!/usr/bin/env bash
# Author-side harness: run the three-way local gate plus the probes for
# `kargo-release-notes` and capture the raw output for gates/<task>-local.txt.
#
# Usage: bash experiments/wildskills25-20261001/gates-kargo-local.sh
set -uo pipefail

REPO="/workspace/skillEvaluation"
TASK="$REPO/wildskills/dynamic_eval/tasks/kargo-release-notes"
FIXED="$REPO/wildskills/dynamic_eval/fixed_skills/kargo-release-notes/environment/skills/akuity-kargo-claude-skills-release-notes-skill-md"
PRIS="$TASK/environment/skills/akuity-kargo-claude-skills-release-notes-skill-md"
ROOT="/tmp/wst25/kargo-release-notes"
VERIFIER="$TASK/verifier/verify_kargo_release_notes.py"

new_workspace() {  # new_workspace <dir>
  local dir="$1"
  rm -rf "$dir"
  mkdir -p "$dir"
  cp -R "$TASK/environment/workspace/." "$dir/"
  chmod +x "$dir"/*.sh
  bash "$dir/build_fixture.sh" "$dir" >/dev/null 2>&1
}

# render_notes <workspace> -- draft RELEASE-NOTES.md from the metadata records present
render_notes() {
  local ws
  ws="$1"
  local repo meta work base tip prev_tag pr title login
  repo="$ws/kargo"
  meta="$ws/metadata"
  work="$ws/.notes-work"
  mkdir -p "$work"   # build_state already populated it; never wipe it here
  base=$(git -C "$repo" merge-base main release-1.9)
  tip=$(git -C "$repo" rev-parse main)
  git -C "$repo" log --oneline --no-merges "$base".."$tip" \
    | grep -E ':\(.*\(#[0-9]+\)' >/dev/null 2>&1 || true
  {
    echo "# Kargo v1.10.0"; echo
    echo "🚀 Kargo v1.10.0 is here — thanks to everyone who promoted, verified and"
    echo "reported their way to this release."; echo
    echo "## ✨ What's new"; echo
    while IFS= read -r pr; do
      [ -n "$pr" ] || continue
      title=$(jq -r 'select(.fetch_failed != true) | .title // empty' "$meta/pr-$pr.json" 2>/dev/null)
      [ -n "$title" ] || continue
      printf -- '- %s ([#%s](https://github.com/akuity/kargo/pull/%s))\n' "$title" "$pr" "$pr"
    done < "$work/included_prs.txt"
    echo
    echo "## 🙏 Special Thanks"; echo
    echo "Welcome to the first-time contributors in this release:"; echo
    for login in $(cut -d'|' -f2 "$work/thanks.txt" 2>/dev/null | sort -u); do
      [ -n "$login" ] || continue
      printf -- '- @%s\n' "$login"
    done
    echo
    prev_tag=$(git -C "$repo" tag --list 'v1.9.*' --sort=-v:refname | head -1)
    echo "**Full Changelog**: [${prev_tag:-v1.9}...v1.10.0](https://github.com/akuity/kargo/compare/${prev_tag:-v1.9}...v1.10.0)"
  } > "$ws/RELEASE-NOTES.md"
}

# localize_script <src> <dst> -- bash 3.2 hosts have no `mapfile` builtin (the task image
# ships bash 5.2). Rewrite that one pre-existing line so the same scripts can be replayed here.
localize_script() {
  local src dst
  src="$1"; dst="$2"
  if [ "${BASH_VERSINFO[0]:-0}" -ge 4 ]; then
    cp "$src" "$dst"
    return 0
  fi
  python3 - "$src" "$dst" <<'PY'
import sys
from pathlib import Path
old = "mapfile -t pr_numbers < <(printf '%s\\n' \"${pr_numbers[@]}\" | sort -un)"
new = ("__pr_sorted=$(printf '%s\\n' \"${pr_numbers[@]:-}\" | sort -un)\n"
       "pr_numbers=()\n"
       "while IFS= read -r __pr_line; do pr_numbers+=(\"$__pr_line\"); done <<<\"$__pr_sorted\"")
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
text = src.read_text()
dst.write_text(text.replace(old, new) if old in text else text)
PY
}

# build_state <workspace> <fetch-script> <map-script> <classify-script>
build_state() {
  local ws fetch map classify repo pipeline work base tip
  ws="$1"; fetch="$2"; map="$3"; classify="$4"
  repo="$ws/kargo"; pipeline="$ws/pipeline"; work="$ws/.notes-work"
  mkdir -p "$pipeline" "$ws/metadata" "$work"
  localize_script "$fetch" "$pipeline/fetch-pr-metadata.sh"
  localize_script "$map" "$pipeline/map-contributors.sh"
  localize_script "$classify" "$pipeline/classify-by-subject.sh"
  chmod +x "$pipeline"/*.sh
  if ! command -v gh >/dev/null 2>&1; then
    mkdir -p "$work/bin"
    ln -sf "$ws/gh-shim.sh" "$work/bin/gh"
    export PATH="$work/bin:$PATH"
  fi
  export KARGO_REPO_ROOT="$repo" KARGO_FIXTURE_DIR="$ws/fixture" KARGO_GH_FAIL_PRS=1523
  # each probe run gets its own transient-failure state, so the first request really fails
  export KARGO_GH_STATE_FILE="$work/gh-state.txt"
  rm -f "$KARGO_GH_STATE_FILE"
  base=$(git -C "$repo" merge-base main release-1.9)
  tip=$(git -C "$repo" rev-parse main)
  git -C "$repo" log --oneline --no-merges "$base".."$tip" > "$work/range.txt"
  ( cd "$repo" && bash "$pipeline/classify-by-subject.sh" "$work/range.txt" \
      "$work/included.txt" "$work/excluded.txt" "$work/uncertain.txt" ) >/dev/null 2>&1
  ( cd "$repo" && bash "$pipeline/fetch-pr-metadata.sh" "$work/range.txt" "$ws/metadata" ) \
      > "$work/fetch.out" 2> "$work/fetch.err"
  ( cd "$repo" && KARGO_METADATA_DIR="$ws/metadata" \
      bash "$pipeline/map-contributors.sh" "$base" "$tip" release-1.9 ) \
      > "$work/contributors.txt" 2> "$work/contributors.err"
  git -C "$repo" log --oneline --no-merges "$base".."$tip" \
    | grep -E ':.*\(#[0-9]+\)\s*$' \
    | grep -Ei '(^| )(feat|fix)(\(|:)' \
    | grep -vEi 'chore|backport|Merge commit from fork|refactor|deps|\(ci\)|docs' \
    | sed -E 's/.*\(#([0-9]+)\)\s*$/\1/' | sort -un > "$work/included_prs.txt"
  grep -E '^[^|]+\|[^|]+$' "$work/contributors.txt" | sort -u > "$work/thanks.txt" || true
  render_notes "$ws"
}

score() {  # score <label> <workspace>
  echo "reward=$1 workspace=$2"
  WST25_WORKSPACE="$2" WST25_LOGS="$ROOT/$1/logs" python3 "$VERIFIER"
}

echo "=============================================================="
echo "(a) ORACLE: oracle/solve.sh, three consecutive runs"
echo "=============================================================="
for i in 1 2 3; do
  new_workspace "$ROOT/oracle/workspace"
  echo "--- oracle run #$i"
  WST25_WORKSPACE="$ROOT/oracle/workspace" WST25_ORACLE_SKILLS="$FIXED" KARGO_GH_FAIL_PRS=1523 \
    bash "$TASK/oracle/solve.sh" "$ROOT/oracle/workspace" 2>&1 | sed 's/^/    /'
  echo "--- delivered pipeline is byte-identical to the overlay:"
  for f in fetch-pr-metadata.sh map-contributors.sh classify-by-subject.sh; do
    printf '    %s: ' "$f"
    cmp -s "$ROOT/oracle/workspace/pipeline/$f" "$FIXED/scripts/$f" && echo identical || echo DIFFERS
  done
  WST25_WORKSPACE="$ROOT/oracle/workspace" WST25_LOGS="$ROOT/oracle/logs" python3 "$VERIFIER" \
    | sed 's/^/    /'
done

echo
echo "=============================================================="
echo "(b) PRISTINE: ship the skill's own scripts unchanged"
echo "=============================================================="
new_workspace "$ROOT/pristine/workspace"
build_state "$ROOT/pristine/workspace" "$PRIS/scripts/fetch-pr-metadata.sh" \
  "$PRIS/scripts/map-contributors.sh" "$PRIS/scripts/classify-by-subject.sh"
echo "--- pristine fetch summary:"; tail -4 "$ROOT/pristine/workspace/.notes-work/fetch.err"
echo "--- pristine pr-1523.json: $(head -c 60 "$ROOT/pristine/workspace/metadata/pr-1523.json")"
echo "--- pristine contributor mapping:"
cat "$ROOT/pristine/workspace/.notes-work/contributors.txt" | sed 's/^/    /'
score pristine "$ROOT/pristine/workspace" | sed 's/^/    /'

echo
echo "=============================================================="
echo "(c) EMPTY workspace: nothing delivered"
echo "=============================================================="
rm -rf "$ROOT/empty"; mkdir -p "$ROOT/empty/workspace"
score empty "$ROOT/empty/workspace" | sed 's/^/    /'

echo
echo "=============================================================="
echo "(d) ANTI-HARDCODING probe: a hand-written draft + hand-written metadata that imitate a"
echo "    correct run on the visible checkout, but ship the pristine scripts"
echo "=============================================================="
new_workspace "$ROOT/hardcoded/workspace"
build_state "$ROOT/hardcoded/workspace" "$PRIS/scripts/fetch-pr-metadata.sh" \
  "$PRIS/scripts/map-contributors.sh" "$PRIS/scripts/classify-by-subject.sh"
# the probe author hand-fixes the visible artifacts (titles + logins) but not the scripts
python3 - "$ROOT/hardcoded/workspace" <<'PY'
import json, re, sys
from pathlib import Path
ws = Path(sys.argv[1]); meta = ws / "metadata"
spec = json.loads((ws / "gh-fixture.json").read_text())
by_num = {p["number"]: p for p in spec["prs"]}
for num, pr in by_num.items():
    f = meta / f"pr-{num}.json"
    if f.is_file() and not json.loads(f.read_text()).get("title"):
        f.write_text(json.dumps({"title": pr["title"], "body": pr["body"],
                                 "labels": [{"name": n} for n in pr["labels"]],
                                 "author": {"login": pr["author"]["login"]}},
                                ensure_ascii=False, indent=2) + "\n")
base = json.loads((ws / "fixture" / "gh-fixture.json").read_text())
ok = [1511, 1540, 1551, 1556, 1567, 1572, 1578, 1582, 1526, 1548, 1581, 1583, 1523]
lines = [f"- {by_num[n]['title']} ([#{n}](https://github.com/akuity/kargo/pull/{n}))" for n in ok if n in by_num]
(ws / "RELEASE-NOTES.md").write_text(
    "# Kargo v1.10.0\n\n🚀 Kargo v1.10.0 is here.\n\n## ✨ What's new\n\n" + "\n".join(lines) +
    "\n\n## 🙏 Special Thanks\n\n" + "\n".join(f"- @{by_num[n]['author']['login']}" for n in ok if n in by_num) +
    "\n\n**Full Changelog**: [v1.9.4...v1.10.0](https://github.com/akuity/kargo/compare/v1.9.4...v1.10.0)\n")
print("probe: hand-wrote", len(lines), "bullets and the metadata")
PY
score hardcoded "$ROOT/hardcoded/workspace" | sed 's/^/    /'

echo
echo "=============================================================="
echo "(e) PARTIAL FIX probe: fetch repaired, map-contributors still emits UNKNOWN"
echo "=============================================================="
new_workspace "$ROOT/partial/workspace"
python3 - "$PRIS/scripts/map-contributors.sh" "$ROOT/partial/map-contributors.sh" <<'PY'
import sys
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
# the pristine mapping: no metadata fallback, so the null-author contributor stays UNKNOWN
dst.write_text(src.read_text())
PY
build_state "$ROOT/partial/workspace" "$FIXED/scripts/fetch-pr-metadata.sh" \
  "$ROOT/partial/map-contributors.sh" "$FIXED/scripts/classify-by-subject.sh"
score partial "$ROOT/partial/workspace" | sed 's/^/    /'

echo
echo "=============================================================="
echo "(f) OVERLAY / STRUCTURE / DEPS"
echo "=============================================================="
echo "--- diff -rq tasks/<task>/environment/skills fixed_skills/<task>/environment/skills"
diff -rq "$TASK/environment/skills" \
  "$REPO/wildskills/dynamic_eval/fixed_skills/kargo-release-notes/environment/skills" || true
echo "--- grep -c 'COPY.*skills' environment/Dockerfile"
grep -c "COPY.*skills" "$TASK/environment/Dockerfile"
echo "--- overlay must not mention task paths / verifier names / fixture values:"
grep -rniE "app/workspace|verify_|oracle|1503|1557|1586|2108|2101|alice-chen" \
  "$REPO/wildskills/dynamic_eval/fixed_skills/kargo-release-notes/environment/skills" \
  | grep -v "^Binary" || echo "    (no hits)"
echo "--- structural gate + dependency lint (read-only entry points)"
python3 - "$REPO" <<'PY'
import json, sys
from pathlib import Path
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "experiments" / "wildskills25-20261001"))
import validate_tasks, check_deps
entry = {"task": "kargo-release-notes",
         "skill": "akuity-kargo-claude-skills-release-notes-skill-md"}
print("validate_tasks.check_task ->")
print(json.dumps(validate_tasks.check_task(entry), ensure_ascii=False, indent=1))
print("check_deps.check ->")
print(json.dumps(check_deps.check(entry), ensure_ascii=False, indent=1))
PY
echo "done."
