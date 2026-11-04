#!/usr/bin/env python3
"""Scaffold one wildskills13 task package with the repository's conventions.

Creates (never overwrites) under wildskills/dynamic_eval/tasks/<task>/:
  task.md, environment/Dockerfile, verifier/test.sh, verifier/verify_<task>.py, oracle/solve.sh

The verifier stub already emits the exact artifact contract benchflow consumes
(/logs/verifier/{ctrf.json,reward.txt,reward.json,verifier-detail.json}, reward = passed/total),
so the only thing left to write per task is the CHECK list.

Usage:
  python3 scaffold_task.py <task-name> --skill <source-skill-dir> [--difficulty easy|medium|hard]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path('/workspace/skillEvaluation')
TASKS = REPO / 'wildskills' / 'dynamic_eval' / 'tasks'
FIXED = REPO / 'wildskills' / 'dynamic_eval' / 'fixed_skills'

TASK_MD = """---
schema_version: '1.3'
metadata:
  author_name: wildskills13-audit
  author_email: n/a
  difficulty: {difficulty}
  category: software-engineering
  subcategory: {subcategory}
  category_confidence: high
  task_type:
  - tool-use
  modality:
  - {modality}
  interface:
  - terminal
  skill_type:
  - tool-workflow
  tags:
  - {tags}
verifier:
  type: test-script
  timeout_sec: 300.0
  service: main
  hardening:
    cleanup_conftests: true
agent:
  timeout_sec: 900.0
sandbox:
  network_mode: public
  build_timeout_sec: 600.0
  workdir: /app/{workdir}
  os: linux
  cpus: 1
  memory_mb: 2048
  storage_mb: 10240
  gpus: 0
---

<!-- TODO(task.md): 用户口吻的请求。必须满足：
     (1) 产物必须经由被审计的 skill 脚本路径才能自然产出（不修就交不出 / 算错）；
     (2) 明确写出期望的输出路径；
     (3) 让"自己重写一套"比"用 skill"更贵（数据量/规则复杂度）；
     (4) 末段固定写：一个用于…的技能（`{skill}`）已为本任务安装。使用前请先读它的 `SKILL.md`，
         并自行判断是直接使用、改造还是绕过它。 -->

我的工作目录是 `/app/{workdir}`，……

请完成以下工作：

1. ……

要求：

- ……
- 一个用于……的技能（`{skill}`）已为本任务安装。使用前请先读它的 `SKILL.md`，并自行判断是直接使用、改造还是绕过它。
"""

DOCKERFILE = """FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \\
    python3 \\
    python3-pip \\
    ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

# TODO(environment): 预装任务路径上的所有其它工具（G1 环境洁癖：只留目标缺陷）。
# 离线任务不要在这里装需要联网的东西；agent 运行时不联网。

WORKDIR /app/{workdir}
COPY {workdir}/ /app/{workdir}/

# NOTE: do NOT copy environment/skills into the image. The driver uploads the skill tree
# at run time to /app/skills (symlinked as ~/.claude/skills and ~/.agents/skills):
#   OriginalSkill -> tasks/<task>/environment/skills
#   FixedSkill    -> fixed_skills/<task>/environment/skills
# Baking it in would give the NoSkill arm the skill and make the arms identical.

CMD ["/bin/bash"]
"""

TEST_SH = """#!/bin/bash
# Dependency-free verifier wrapper: only needs python3 from the task image.
mkdir -p /logs/verifier
python3 /verifier/verify_{mod}.py
exit 0
"""

VERIFIER = '''#!/usr/bin/env python3
"""Dynamic verifier for the `{task}` task.

Audited inconsistency exercised here (see experiments/wildskills13-20260929/tasks.json):
  <doc claim>  vs  <implementation behaviour>
so the artifact below can only be right when the agent routes around (or fixes) the defect.

Checks (reward = passed / total):
  TODO: one line per check, naming what it proves.

Local (docker-free) testing: override the two path constants through the environment,
  WST13_WORKSPACE=<scratch dir> WST13_LOGS=<scratch logs> python3 verify_{mod}.py
The container run passes neither, so it uses the real /app/{workdir} and /logs/verifier.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

WORKSPACE = Path(os.environ.get("WST13_WORKSPACE", "/app/{workdir}"))
LOGS = Path(os.environ.get("WST13_LOGS", "/logs/verifier"))


# --------------------------------------------------------------------------- checks
def check_placeholder():
    """TODO: replace with the real checks."""
    return False, "not implemented"


CHECKS = [
    ("placeholder", check_placeholder),
]


# --------------------------------------------------------------------------- harness
def run_checks():
    results = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, "check crashed: " + type(exc).__name__ + ": " + str(exc)
        results.append((name, bool(ok), detail))
    return results


def write_outputs(results):
    started = time.time()
    tests = [{{"name": f"::test_{{name}}", "status": "passed" if ok else "failed",
              "duration": 0.0, "start": started, "stop": started, "retries": 0,
              "file_path": "verify_{mod}.py"}} for name, ok, _ in results]
    passed = sum(1 for _, ok, _ in results if ok)
    reward = round(passed / len(tests), 4) if tests else 0.0
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "ctrf.json").write_text(json.dumps({{"results": {{
        "tool": {{"name": "verify_{mod}", "version": "1.0"}},
        "summary": {{"tests": len(tests), "passed": passed, "failed": len(tests) - passed,
                    "skipped": 0, "pending": 0, "other": 0,
                    "start": started, "stop": time.time()}},
        "tests": tests}}}}, ensure_ascii=False, indent=1))
    (LOGS / "reward.txt").write_text(str(reward) + "\\n")
    (LOGS / "reward.json").write_text(json.dumps({{"reward": reward}}, indent=2) + "\\n")
    (LOGS / "verifier-detail.json").write_text(json.dumps(
        {{"checks": [{{"name": n, "passed": p, "detail": d}} for n, p, d in results]}},
        ensure_ascii=False, indent=2) + "\\n")
    print(f"reward={{reward}} ({{passed}}/{{len(tests)}} checks passed)")
    for name, ok, why in results:
        print(f"  [{{'PASS' if ok else 'FAIL'}}] {{name}}: {{why}}")
    return reward


def main():
    write_outputs(run_checks())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

SOLVE = """#!/bin/bash
set -euo pipefail

# Reference (oracle) solution for the `{task}` task.
#
# It must produce the fully-correct artifact WITHOUT going through the audited defect,
# so that `oracle/solve.sh` scores 1.0 and G0 (verifier self-proof) passes 3/3.
#
# TODO(oracle): implement the correct path (usually: do the work the way the SKILL.md
# promises, instead of the way the buggy script does it).

echo "TODO: oracle for {task}" >&2
exit 1
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('task')
    ap.add_argument('--skill', required=True, help='source skill dir name (for the task.md sentence)')
    ap.add_argument('--subcategory', default='skill-consistency')
    ap.add_argument('--difficulty', default='medium', choices=['easy', 'medium', 'hard'])
    ap.add_argument('--workdir', default='workspace')
    ap.add_argument('--modality', default='json')
    ap.add_argument('--tags', default='skill')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    base = TASKS / args.task
    mod = args.task.replace('-', '_')
    files = {
        base / 'task.md': TASK_MD.format(**vars(args)),
        base / 'environment' / 'Dockerfile': DOCKERFILE.format(**vars(args)),
        base / 'verifier' / 'test.sh': TEST_SH.format(mod=mod, task=args.task),
        base / 'verifier' / f'verify_{mod}.py': VERIFIER.format(mod=mod, task=args.task,
                                                               workdir=args.workdir),
        base / 'oracle' / 'solve.sh': SOLVE.format(task=args.task),
    }
    for path, content in files.items():
        if path.exists() and not args.force:
            print(f'skip (exists): {path.relative_to(REPO)}')
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if path.suffix == '.sh':
            path.chmod(0o755)
        print(f'wrote {path.relative_to(REPO)}')
    print(f'\nnext: copy the pristine skill tree into '
          f'{(base / "environment" / "skills" / args.skill).relative_to(REPO)}')
    print(f'      and create the repaired overlay at {(FIXED / args.task).relative_to(REPO)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
