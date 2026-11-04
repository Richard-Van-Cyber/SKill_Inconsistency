#!/usr/bin/env python3
"""Three-arm re-run of the 10 DRS tasks with the v2 (trace-driven, doc-only) repair.

Design
------
Arms:      NoSkill / OriginalSkill / RepairV2
Cells:     10 tasks x 3 arms x 3 repeats = 90
Budget:    60 requests / 1,000,000 cumulative tokens / 32,768 output  (identical to
           haiku45-threeway-20260917, so the numbers are directly comparable)

Only the *skill content* differs from the 2026-09-17 study. Everything else is held
byte-identical:
  * the same `runner-source/*.py` (verified byte-identical to
    haiku45-threeway-20260917/runner-source, which produced the reference arms);
  * the same frozen `inputs/selected_tasks/` packages;
  * the same condition names, so rq3_cli_runner takes the exact same code path.
    `RepairV2` is passed to run_job as `RepairedSkill`, whose skill source is
    `<repaired_root>/<task>/environment/skills`; we point `repaired_root` at
    `inputs/fixed_skills_v2` instead of `inputs/fixed_skills`.

Difference from haiku45-threeway-20260917: that study ran its three arms with
`logical_run_id` = `<task>__<condition>__r<n>`; we keep that shape but add a distinct
`arm_label` so the v2 repair is never confused with the 0917 repair in reports.

    python3 drs_v2_run.py [--workers N] [--cells a,b] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))

# Match haiku45-threeway-20260917 exactly.
os.environ.setdefault('DIRECTED_REPAIR_MAX_REQUESTS', '60')
os.environ.setdefault('DIRECTED_REPAIR_MAX_TOKENS', '1000000')
os.environ.setdefault('DIRECTED_REPAIR_MAX_OUTPUT_TOKENS', '32768')

TASKS = sorted(p.name for p in (STUDY / 'inputs' / 'selected_tasks').iterdir() if p.is_dir())
# Display label -> the condition string rq3_cli_runner understands.
ARMS = [('NoSkill', 'NoSkill'),
        ('OriginalSkill', 'OriginalSkill'),
        ('RepairV2', 'RepairedSkill')]
DEFAULT_REPEATS = 3
CRED = Path('/home/user/project/.secrets/penguin.json')

# Run the four tasks that actually carry a v2 edit first. Two reasons: the decisive
# evidence (does the repair change behaviour on energy/grid?) lands in the first batch
# instead of ~2.5 h in, and all three arms of a task run while the cluster is in the
# same load regime, which tightens the within-task comparison. Order is not a treatment
# variable and every arm sees the identical order, so the design stays balanced.
REPAIRED_FIRST = ['energy-market-pricing', 'grid-dispatch-operator',
                  'civ6-adjacency-optimizer', 'court-form-filling']
TASK_ORDER = ([t for t in REPAIRED_FIRST if t in TASKS] +
              [t for t in TASKS if t not in REPAIRED_FIRST])


def build_jobs(repeats: int):
    jobs = []
    for task in TASK_ORDER:
        for label, cond in ARMS:
            for r in range(1, repeats + 1):
                jobs.append(dict(
                    task=task, arm=label, condition=cond, repeat=r,
                    logical_run_id=f'{task}__{label}__r{r}'))
    return jobs


def sweep_docker():
    """Docker's default address pools run out after ~30 project networks and the runner
    keeps every cell's container after `env.stop(delete=False)`. Sweep only our own
    anonymous/* containers and networks; never touch other users'."""
    try:
        ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'status=exited'],
                                      text=True).split()
    except Exception:
        return
    killed = 0
    for cid in ids:
        try:
            img = subprocess.check_output(
                ['docker', 'inspect', '-f', '{{.Config.Image}}', cid], text=True).strip()
        except Exception:
            continue
        if img.startswith('anonymous/'):
            subprocess.run(['docker', 'rm', '-f', cid], capture_output=True)
            killed += 1
    nets = subprocess.run(['docker', 'network', 'ls', '--format', '{{.Name}}'],
                          capture_output=True, text=True).stdout.split()
    freed = 0
    for n in nets:
        if n.startswith('project-'):
            if subprocess.run(['docker', 'network', 'rm', n],
                              capture_output=True).returncode == 0:
                freed += 1
    print(f'[sweep] removed {killed} exited project containers, {freed} networks')


def preflight_repair(root: Path):
    """Fail fast if the v2 repair is not actually present in the uploaded skill tree.

    Two mistakes are cheap to make and expensive to discover: uploading a stale copy of
    `fixed_skills_v2` (the study dir keeps its own copy under inputs/), and placing a doc
    edit in a file the agent never loads. This asserts the *content* of the repair, so a
    batch can never run 90 cells against an unpatched skill set.

    The five `expected` skill docs are exactly the ones the traces show are both loaded
    and telling the agent to import a package the image does not ship.
    """
    expected = {
        'energy-market-pricing/environment/skills/economic-dispatch/SKILL.md': 'break-system-packages',
        'energy-market-pricing/environment/skills/locational-marginal-prices/SKILL.md': 'break-system-packages',
        'energy-market-pricing/environment/skills/power-flow-data/SKILL.md': 'break-system-packages',
        'grid-dispatch-operator/environment/skills/economic-dispatch/SKILL.md': 'break-system-packages',
        'grid-dispatch-operator/environment/skills/power-flow-data/SKILL.md': 'break-system-packages',
        'civ6-adjacency-optimizer/environment/skills/sqlite-map-parser/SKILL.md': 'does **not** ship the `sqlite3`',
        'court-form-filling/environment/skills/pdf/forms.md': 'python3 scripts/check_fillable_fields',
    }
    missing = [rel for rel, needle in expected.items()
               if not (root / rel).is_file() or needle not in (root / rel).read_text()]
    if missing:
        raise SystemExit('Repair preflight failed -- these skill files are missing the '
                         'expected v2 edit (stale upload?):\n  ' + '\n  '.join(missing))
    # The repaired tree must not have grown or lost any file: a data/script change would
    # alter the image tag and break comparability with the frozen task packages.
    pristine = STUDY / 'inputs' / 'selected_tasks'
    for task in TASKS:
        n_p = sum(1 for f in (pristine / task / 'environment' / 'skills').rglob('*') if f.is_file())
        n_v = sum(1 for f in (root / task / 'environment' / 'skills').rglob('*') if f.is_file())
        if n_p != n_v:
            raise SystemExit(f'{task}: repaired tree has {n_v} files, pristine has {n_p}')
    print(f'[preflight] v2 repair verified in {len(expected)} files; file counts match pristine')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--repeats', type=int, default=DEFAULT_REPEATS)
    ap.add_argument('--cells', default='', help='comma-separated logical_run_ids to run')
    ap.add_argument('--arms', default='',
                    help='comma-separated arm labels to run, e.g. RepairV2. '
                         'NoSkill/OriginalSkill already exist in haiku45-threeway-20260917 '
                         'under an identical config, so only the repaired arm needs re-running.')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    from run_directed_repair import install_proxy_defaults_from_env, check_environment
    from rq3_cli_runner import run_job

    check_environment()
    install_proxy_defaults_from_env()
    preflight_repair(STUDY / 'inputs' / 'fixed_skills_v2')

    jobs = build_jobs(args.repeats)
    if args.arms:
        wanted_arms = {a.strip() for a in args.arms.split(',') if a.strip()}
        unknown = wanted_arms - {label for label, _ in ARMS}
        if unknown:
            raise SystemExit(f'--arms: unknown arm(s) {sorted(unknown)}; '
                             f'known: {[label for label, _ in ARMS]}')
        jobs = [j for j in jobs if j['arm'] in wanted_arms]
    if args.cells:
        wanted = {c.strip() for c in args.cells.split(',') if c.strip()}
        jobs = [j for j in jobs if j['logical_run_id'] in wanted]
        if not jobs:
            raise SystemExit('--cells matched no scheduled job')

    runs = STUDY / 'runs'
    runs.mkdir(exist_ok=True)
    keys = json.loads(CRED.read_text())
    sweep_docker()

    print(f'[v2] study={STUDY.name} cells={len(jobs)} workers={args.workers} '
          f'arms={[a for a, _ in ARMS]} tasks={len(TASKS)}')
    for j in jobs[:6]:
        print(f"  {j['logical_run_id']}  (condition={j['condition']})")
    if len(jobs) > 6:
        print(f'  ... {len(jobs) - 6} more')
    if args.dry_run:
        return 0

    lock = threading.Lock()

    def snapshot():
        with lock:
            rows = []
            for p in sorted(runs.glob('*/result.json')):
                try:
                    rows.append(json.loads(p.read_text()))
                except Exception:
                    pass
            (STUDY / 'summary.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1))
            finished = [r for r in rows if r.get('finished_at')]
            graded = [r for r in rows if r.get('status') == 'graded']
            (STUDY / 'execution-status.json').write_text(json.dumps({
                'status': ('completed' if len(finished) == len(jobs) else 'running'),
                'planned': len(jobs), 'finished': len(finished), 'graded': len(graded),
                'errors': [{'logical_run_id': r.get('logical_run_id'), 'status': r.get('status')}
                           for r in rows if r.get('finished_at') and r.get('status') != 'graded'],
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            }, indent=1))

    def launch(job):
        out_root = runs / job['logical_run_id']
        inner = out_root / (job['task'] + '__claude-haiku')
        if (out_root / 'result.json').exists():
            prev = json.loads((out_root / 'result.json').read_text())
            if prev.get('status') in ('graded', 'verifier_error', 'agent_error'):
                print(f"[skip] {job['logical_run_id']} (already {prev.get('status')})")
                return
        if inner.exists():
            shutil.rmtree(inner)
        out_root.mkdir(parents=True, exist_ok=True)
        settings = SimpleNamespace(
            run_id='drsv2-' + job['logical_run_id'].replace('__', '-'),
            condition=job['condition'],
            repeat=job['repeat'],
            logical_run_id=job['logical_run_id'],
            attempt=1,
            smoke=False,
            repaired_root=STUDY / 'inputs' / 'fixed_skills_v2',
            prepare_verifier_deps=True)
        task_path = STUDY / 'inputs' / 'selected_tasks' / job['task']
        try:
            r = asyncio.run(run_job(settings, out_root, keys, (task_path, 'claude-haiku')))
        except Exception as exc:                      # noqa: BLE001
            r = {'logical_run_id': job['logical_run_id'], 'status': 'crashed',
                 'error': f'{type(exc).__name__}: {exc}',
                 'traceback': traceback.format_exc()[-1500:]}
        r['arm'] = job['arm']
        (out_root / 'result.json').write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        print(f"[done] {job['logical_run_id']} status={r.get('status')} "
              f"score={r.get('score')} api_calls={r.get('api_calls')} "
              f"tok={r.get('total_tokens')}")
        snapshot()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(launch, jobs))

    snapshot()
    rows = [json.loads(p.read_text()) for p in sorted(runs.glob('*/result.json'))]
    print()
    print(f"{'cell':48} {'status':12} {'score':>6} {'calls':>6} {'tok':>9} {'agent_s':>8}")
    for r in sorted(rows, key=lambda x: str(x.get('logical_run_id'))):
        print(f"{str(r.get('logical_run_id')):48} {str(r.get('status')):12} "
              f"{str(r.get('score')):>6} {str(r.get('api_calls')):>6} "
              f"{str(r.get('total_tokens')):>9} {str(r.get('agent_seconds')):>8}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
