#!/usr/bin/env python3
"""Classify cell failures as INFRASTRUCTURE vs PERFORMANCE and retry only the former.

With 135 cells, infrastructure failures happen (credit exhaustion, docker pool, a killed
container, an API hiccup). Retrying them is correct. Retrying a *performance* failure is
not -- that is p-hacking the benchmark. This draws the line explicitly:

  INFRASTRUCTURE (retry):
    - status `crashed`, `environment_error`, `model_identity_error`
    - `agent_error` whose error mentions a docker/compose failure or whose cli_exit_code
      is 137 (SIGKILL -- our own cleanup, or an OOM)
    - `agent_error` with cli_exit_code 0 and error == repr(task)  (the archive_artifacts
      KeyError, now fixed upstream)
    - `verifier_error` whose error mentions rc=137 / no reward file but whose agent phase
      succeeded

  PERFORMANCE (keep):
    - `agent_timeout`   -- the agent used its whole allowance; that IS the measurement
    - any `graded` cell, however low the score
    - `agent_error` with a genuine CLI failure not attributable to the above

    python3 analysis_tools/classify_failures.py --study experiments/multi25-20260925 [--delete]

`--delete` removes the retriable cells' directories so the driver re-runs them.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

INFRA_STATUS = {'crashed', 'environment_error', 'model_identity_error'}
# `verifier_error` usually means the verifier never produced a score (it crashed, or its
# dependency bootstrap failed -- e.g. the uv installer needs github, which this sandbox
# cannot reach). That is infrastructure: the agent's work was not measured, so re-running
# yields a real observation rather than a re-roll of a bad score.
#
# NOT all verifier_errors are retriable though. If a task's own test.sh never asks pytest
# for a ctrf report, the harness will *always* discard its shell reward (by design -- a
# bare exit-code reward hides skipped tests). Re-running such a task is pointless: the same
# deterministic rule fires again. `no_ctrf(task)` detects that and the cell is kept.
# `agent_timeout` is likewise kept: that IS the measurement.
VERIFIER_STATUS = {'verifier_error'}
_STUDY_ROOT = None


def no_ctrf(task: str) -> bool:
    """True if the task's test.sh cannot produce a ctrf.json (so verifier_error is by design)."""
    if _STUDY_ROOT is None:
        return False
    for base in (_STUDY_ROOT / 'inputs' / 'selected_tasks', Path('tasks')):
        sh = base / task / 'verifier' / 'test.sh'
        if sh.is_file():
            try:
                return 'ctrf' not in sh.read_text(errors='replace')
            except Exception:
                return False
    return False
INFRA_ERROR_HINTS = (
    'docker compose command failed',
    'no reward file found',
    'rc=137',
    'externally-managed-environment',   # leaked through as an agent error
    'connection refused',
    'temporary failure in name resolution',
    'permission denied while trying to connect',
)


def classify(r: dict, task: str):
    status = r.get('status')
    err = str(r.get('error') or '')
    tr = str(r.get('termination_reason') or '')
    rc = r.get('cli_exit_code')
    low = err.lower()

    if status == 'graded':
        return 'keep', 'graded'
    if tr == 'agent_timeout' or status == 'agent_error' and tr == 'agent_timeout':
        return 'keep', 'agent_timeout (performance outcome)'
    if status == 'agent_timeout':
        return 'keep', 'agent_timeout (performance outcome)'
    if status in INFRA_STATUS:
        return 'retry', f'{status} (infrastructure)'
    if status in VERIFIER_STATUS:
        if no_ctrf(task):
            return 'keep', f'{status} (test.sh emits no ctrf -> harness rule, not infrastructure)'
        return 'retry', f'{status} (verifier produced no score)'
    if any(h in low for h in INFRA_ERROR_HINTS):
        return 'retry', f'{status} ({err[:60]})'
    if status == 'agent_error' and rc == 137:
        return 'retry', 'agent_error cli_exit_code=137 (SIGKILL)'
    if status == 'agent_error' and rc == 0 and err.strip() in (f"'{task}'", f'"{task}"'):
        return 'retry', 'archive_artifacts KeyError (harness bug)'
    if status in (None, 'agent_running'):
        return 'keep', 'in flight'
    return 'keep', f'{status} (not clearly infrastructure)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--study', required=True)
    ap.add_argument('--delete', action='store_true')
    args = ap.parse_args()
    study = Path(args.study)
    global _STUDY_ROOT
    _STUDY_ROOT = study.resolve()
    runs = study / 'runs'
    if not runs.is_dir():
        raise SystemExit(f'no runs dir at {runs}')

    retry, keep = [], []
    reasons = Counter()
    for cell in sorted(p for p in runs.iterdir() if p.is_dir()):
        rj = cell / 'result.json'
        if not rj.exists():
            continue
        try:
            r = json.loads(rj.read_text())
        except Exception:
            retry.append(cell); reasons['unreadable result.json'] += 1; continue
        task = cell.name.split('__')[0]
        verdict, why = classify(r, task)
        reasons[why] += 1
        (retry if verdict == 'retry' else keep).append(cell)

    print(f'{"cell":48}{"status":22}reason')
    print('-' * 110)
    for cell in sorted(retry):
        r = json.loads((cell / 'result.json').read_text())
        _, why = classify(r, cell.name.split('__')[0])
        print(f'{cell.name:48}{str(r.get("status")):22}{why}')
    print(f'\nretry={len(retry)}  keep={len(keep)}')
    print('reasons:')
    for k, v in reasons.most_common():
        print(f'   {v:>4}  {k}')

    if args.delete and retry:
        for cell in retry:
            shutil.rmtree(cell, ignore_errors=True)
        print(f'\ndeleted {len(retry)} retriable cell dirs; re-run the driver to pick them up')


if __name__ == '__main__':
    main()
