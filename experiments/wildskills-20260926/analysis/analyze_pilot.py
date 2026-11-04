#!/usr/bin/env python3
"""Aggregate the wildskills pilot study into a per-check / per-arm table.

Reads runs/<cell>/result.json plus the verifier's own verifier-detail.json, so the
per-check breakdown comes from the verifier that actually ran, not from a re-scoring.
"""
from __future__ import annotations

import collections
import glob
import json
import tarfile
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
RUNS = STUDY / 'runs'
ARMS = ['NoSkill', 'OriginalSkill', 'FixedSkill']
CHECKS = ['get_call', 'get_stream', 'get_history_path_variable', 'post_save_body',
          'delete_history_path_variable', 'get_models_list', 'request_target_ascii']


def iter_runs():
    for path in sorted(RUNS.glob('*/result.json')):
        outer = json.loads(path.read_text())
        arm = outer.get('arm') or path.parent.name.split('__')[1]
        inner = next(path.parent.glob('*/benchflow/verifier/verifier-detail.json'), None)
        checks = {}
        if inner and inner.exists():
            detail = json.loads(inner.read_text())
            checks = {c['name']: c for c in detail.get('checks', [])}
        artifact = next(path.parent.glob('*/agent-artifacts.tgz'), None)
        yield outer, arm, checks, artifact


def artifact_http(tgz):
    if not tgz or not tgz.exists():
        return None
    with tarfile.open(tgz) as tar:
        for member in tar.getmembers():
            if member.name.endswith('basic/chat/chat.http'):
                return tar.extractfile(member).read().decode('utf-8', 'replace')
    return None


def main():
    rows = list(iter_runs())
    print(f'{"cell":46} {"arm":15} {"score":>7}  fails')
    for outer, arm, checks, _ in rows:
        failed = [n for n in CHECKS if not checks.get(n, {}).get('passed')]
        print(f'{outer["logical_run_id"]:46} {arm:15} {outer["score"]:>7}  {",".join(failed) or "-"}')

    print('\nper-check pass rate by arm')
    header = '  '.join(f'{c[:14]:>14}' for c in CHECKS)
    print(f'{"arm":15} {"n":>2}  {header}')
    for arm in ARMS:
        group = [c for _, a, c, _ in rows if a == arm]
        cells = [f'{sum(1 for g in group if g.get(n, {}).get("passed"))}/{len(group)}' for n in CHECKS]
        print(f'{arm:15} {len(group):>2}  ' + '  '.join(f'{v:>14}' for v in cells))

    print('\nper-arm summary')
    for arm in ARMS:
        group = [(o, c) for o, a, c, _ in rows if a == arm]
        scores = [o['score'] for o, _ in group]
        print(f'{arm:15} n={len(scores)} mean={sum(scores)/len(scores):.4f} '
              f'scores={[round(s, 4) for s in scores]} '
              f'turns={sum(o.get("num_turns") or 0 for o, _ in group) / len(group):.1f} '
              f'sec={sum(o.get("agent_seconds") or 0 for o, _ in group) / len(group):.1f} '
              f'tokens={sum(o.get("total_tokens") or 0 for o, _ in group)} '
              f'usd={sum(o.get("cli_total_cost_usd") or 0 for o, _ in group):.4f}')

    print('\nstatus / termination')
    for outer, arm, _, _ in rows:
        print(f'  {outer["logical_run_id"]:46} status={outer["status"]:8} '
              f'term={outer.get("termination_reason")} models={outer.get("observed_models")} '
              f'budget_stop={outer.get("budget_stop_reason")}')

    print('\nrequest targets per arm (from verifier-detail parsed section)')
    for outer, arm, _, artifact in rows:
        text = artifact_http(artifact)
        if not text:
            print(f'  {outer["logical_run_id"]}: no artifact')
            continue
        lines = [l for l in text.splitlines() if l.strip() and not l.startswith('#')]
        print(f'  {outer["logical_run_id"]}:')
        for line in lines:
            if line.startswith(('GET', 'POST', 'DELETE', 'PUT')):
                print(f'     {line[:150]}')

    out = STUDY / 'analysis' / 'pilot-cells.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([{**o, 'arm': a, 'checks': {k: v.get('passed') for k, v in c.items()}}
                               for o, a, c, _ in rows], ensure_ascii=False, indent=1) + '\n')
    print(f'\nwrote {out}')


if __name__ == '__main__':
    main()
