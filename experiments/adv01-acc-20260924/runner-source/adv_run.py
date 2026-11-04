#!/usr/bin/env python3
"""Drive the paired adversarial cells for the earthquake skill experiment.

Runs from <study>/runner-source/ so that run_agents.ROOT resolves to <study>
(which owns the .runtime/official-cli mount and the .runtime verifier cache).

Cells: {shipped task, adversarial task} x {OriginalSkill, RepairedSkill} x 3 repeats.

    python3 adv_run.py [--workers N] [--cells id,id] [--dry-run]

Budget is pinned to the primary three-way study (60 req / 1M tok / 32K out) so
the numbers are directly comparable with the NoSkill/OriginalSkill/RepairedSkill
arms already collected.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import os
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
CONDITIONS = ['OriginalSkill', 'RepairedSkill']
DEFAULT_REPEATS = 3
CRED = Path('/home/user/project/.secrets/penguin.json')


def build_jobs(repeats: int):
    jobs = []
    for task in TASKS:
        for cond in CONDITIONS:
            for r in range(1, repeats + 1):
                jobs.append(dict(
                    task=task, condition=cond, repeat=r,
                    logical_run_id=f'{task}__{cond}__r{r}'))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--repeats', type=int, default=DEFAULT_REPEATS)
    ap.add_argument('--cells', default='', help='comma-separated logical_run_ids to run')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    from run_directed_repair import install_proxy_defaults_from_env, check_environment
    from rq3_cli_runner import run_job

    check_environment()
    install_proxy_defaults_from_env()

    jobs = build_jobs(args.repeats)
    if args.cells:
        wanted = {c.strip() for c in args.cells.split(',') if c.strip()}
        jobs = [j for j in jobs if j['logical_run_id'] in wanted]
        if not jobs:
            raise SystemExit('--cells matched no scheduled job')

    runs = STUDY / 'runs'
    runs.mkdir(exist_ok=True)
    keys = json.loads(CRED.read_text())

    # Docker's default address pools run out after ~30 project networks, and the
    # runner keeps every cell's container after `env.stop(delete=False)` so the
    # evidence survives. Without this sweep the next batch dies with
    # "all predefined address pools have been fully subnetted" and the whole
    # batch must be re-run -- which is why these batches were serialised. Sweep
    # only our own anonymous/* containers and networks; never touch other users'.
    def sweep_docker():
        import subprocess
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

    sweep_docker()

    print(f'[adv] study={STUDY.name} cells={len(jobs)} workers={args.workers}')
    for j in jobs:
        print(f"  {j['logical_run_id']}")
    if args.dry_run:
        return 0

    lock = threading.Lock()
    done = []

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
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            }, indent=1))

    def launch(job):
        out_root = runs / job['logical_run_id']
        # A cell counts as done only when run_job actually produced a result.
        # run_job does a bare `out.mkdir()`, so a leftover directory from an
        # earlier failed attempt makes it die with FileExistsError.
        inner = out_root / (job['task'] + '__claude-haiku')
        if (out_root / 'result.json').exists():
            prev = json.loads((out_root / 'result.json').read_text())
            if prev.get('status') in ('graded', 'verifier_error', 'agent_error'):
                print(f"[skip] {job['logical_run_id']} (already {prev.get('status')})")
                return
        if inner.exists():
            import shutil
            shutil.rmtree(inner)
        out_root.mkdir(parents=True, exist_ok=True)
        settings = SimpleNamespace(
            run_id='adv01-' + job['logical_run_id'].replace('__', '-'),
            condition=job['condition'],
            repeat=job['repeat'],
            logical_run_id=job['logical_run_id'],
            attempt=1,
            smoke=False,
            repaired_root=STUDY / 'inputs' / 'fixed_skills',
            prepare_verifier_deps=True)
        task_path = STUDY / 'inputs' / 'selected_tasks' / job['task']
        try:
            r = asyncio.run(run_job(settings, out_root, keys, (task_path, 'claude-haiku')))
        except Exception as exc:                      # noqa: BLE001
            r = {'logical_run_id': job['logical_run_id'], 'status': 'crashed',
                 'error': f'{type(exc).__name__}: {exc}',
                 'traceback': traceback.format_exc()[-1500:]}
        (out_root / 'result.json').write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        with lock:
            done.append(r)
        print(f"[done] {job['logical_run_id']} status={r.get('status')} "
              f"score={r.get('score')} api_calls={r.get('api_calls')}")
        snapshot()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(launch, jobs))

    snapshot()
    rows = [json.loads(p.read_text()) for p in sorted(runs.glob('*/result.json'))]
    print()
    print(f"{'cell':70} {'status':10} {'score':>6} {'calls':>6} {'agent_s':>8}")
    for r in sorted(rows, key=lambda x: str(x.get('logical_run_id'))):
        print(f"{str(r.get('logical_run_id')):70} {str(r.get('status')):10} "
              f"{str(r.get('score')):>6} {str(r.get('api_calls')):>6} {str(r.get('agent_seconds')):>8}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
