#!/usr/bin/env python3
"""Drive the 15-task extension of the three-arm study (25 tasks total with the original 10).

Arms: NoSkill / OriginalSkill / RepairedSkill   (15 tasks x 3 arms x 3 trials = 135 cells)
Budget: 60 requests / 1,000,000 tokens / 32,768 output -- identical to
        haiku45-threeway-20260917, and the same runner sources byte-for-byte, so these
        cells are directly comparable with the original 10 tasks' cells.

Phases (run separately so the repair can be designed from THIS study's OriginalSkill
traces rather than from another study's):
    --arms NoSkill,OriginalSkill     # phase 1: 90 cells
    --arms RepairedSkill             # phase 3: 45 cells

    python3 multi25_run.py --arms NoSkill,OriginalSkill --workers 3
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

os.environ.setdefault('DIRECTED_REPAIR_MAX_REQUESTS', '60')
os.environ.setdefault('DIRECTED_REPAIR_MAX_TOKENS', '1000000')
os.environ.setdefault('DIRECTED_REPAIR_MAX_OUTPUT_TOKENS', '32768')

TASKS = sorted(p.name for p in (STUDY / 'inputs' / 'selected_tasks').iterdir() if p.is_dir())
ARMS = [('NoSkill', 'NoSkill'),
        ('OriginalSkill', 'OriginalSkill'),
        ('RepairedSkill', 'RepairedSkill')]
DEFAULT_REPEATS = 3
CRED = Path('/home/user/project/.secrets/penguin.json')
REPAIRED_ROOT = STUDY / 'inputs' / 'fixed_skills_v3'


def build_jobs(repeats: int):
    jobs = []
    for task in TASKS:
        for label, cond in ARMS:
            for r in range(1, repeats + 1):
                jobs.append(dict(task=task, arm=label, condition=cond, repeat=r,
                                 logical_run_id=f'{task}__{label}__r{r}'))
    return jobs


def sweep_docker():
    """Release the previous batch's containers/networks. Only ever touches anonymous/*
    (our own project names); the runner keeps containers after env.stop(delete=False)
    so this is what keeps Docker's address pool from filling up."""
    try:
        ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'status=exited'],
                                      text=True).split()
    except Exception:
        return 0, 0
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
    # MUST return a pair: the periodic call site does `k, f = sweep_docker()`. Returning
    # None here crashed every launch that happened to land on a sweep multiple
    # (TypeError: cannot unpack non-iterable NoneType object), silently dropping cells.
    return killed, freed


def preflight_repair(root: Path):
    """Only meaningful for the repaired arm: assert the uploaded repair really carries
    the edits, and that no file was added or removed (a data/script change would alter
    the image tag and break comparability with the frozen task packages)."""
    expected = json.loads((STUDY / 'inputs' / 'repair_expected.json').read_text())
    missing = [rel for rel, needle in expected.items()
               if not (root / rel).is_file() or needle not in (root / rel).read_text()]
    if missing:
        raise SystemExit('Repair preflight failed -- missing v3 edit in:\n  ' + '\n  '.join(missing))
    pristine = STUDY / 'inputs' / 'selected_tasks'
    for task in TASKS:
        n_p = sum(1 for f in (pristine / task / 'environment' / 'skills').rglob('*') if f.is_file())
        n_v = sum(1 for f in (root / task / 'environment' / 'skills').rglob('*') if f.is_file())
        if n_p != n_v:
            raise SystemExit(f'{task}: repaired tree has {n_v} files, pristine has {n_p}')
    print(f'[preflight] repair verified in {len(expected)} files; file counts match pristine')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--repeats', type=int, default=DEFAULT_REPEATS)
    ap.add_argument('--arms', default='NoSkill,OriginalSkill')
    ap.add_argument('--cells', default='')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    from run_directed_repair import install_proxy_defaults_from_env, check_environment
    from rq3_cli_runner import run_job

    check_environment()
    install_proxy_defaults_from_env()

    wanted_arms = {a.strip() for a in args.arms.split(',') if a.strip()}
    unknown = wanted_arms - {label for label, _ in ARMS}
    if unknown:
        raise SystemExit(f'--arms: unknown {sorted(unknown)}; known {[l for l, _ in ARMS]}')
    if 'RepairedSkill' in wanted_arms:
        preflight_repair(REPAIRED_ROOT)

    jobs = [j for j in build_jobs(args.repeats) if j['arm'] in wanted_arms]
    if args.cells:
        w = {c.strip() for c in args.cells.split(',') if c.strip()}
        jobs = [j for j in jobs if j['logical_run_id'] in w]
        if not jobs:
            raise SystemExit('--cells matched no scheduled job')

    runs = STUDY / 'runs'
    runs.mkdir(exist_ok=True)
    keys = json.loads(CRED.read_text())
    sweep_docker()

    print(f'[multi25] study={STUDY.name} cells={len(jobs)} workers={args.workers} '
          f'tasks={len(TASKS)} arms={sorted(wanted_arms)}')
    for j in jobs[:4]:
        print(f"  {j['logical_run_id']}")
    if len(jobs) > 4:
        print(f'  ... {len(jobs) - 4} more')
    if args.dry_run:
        return 0

    lock = threading.Lock()
    done_count = [0]

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
                'status': 'completed' if len(finished) == len(jobs) else 'running',
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
            if prev.get('status') in ('graded', 'verifier_error'):
                print(f"[skip] {job['logical_run_id']} (already {prev.get('status')})")
                return
        if inner.exists():
            shutil.rmtree(inner, ignore_errors=True)
        out_root.mkdir(parents=True, exist_ok=True)
        settings = SimpleNamespace(
            run_id='m25-' + job['logical_run_id'].replace('__', '-'),
            condition=job['condition'],
            repeat=job['repeat'],
            logical_run_id=job['logical_run_id'],
            attempt=1,
            smoke=False,
            repaired_root=REPAIRED_ROOT,
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
              f"score={r.get('score')} calls={r.get('api_calls')} tok={r.get('total_tokens')}")
        # Docker's default address pools run out after ~30 project networks. The runner
        # releases each cell's network itself, but with many workers in flight that lags
        # behind and later cells die with "all predefined address pools have been fully
        # subnetted" -> environment_error. Sweeping every few completions prevents it.
        with lock:
            done_count[0] += 1
            need_sweep = done_count[0] % 2 == 0
        if need_sweep:
            k, f = sweep_docker()
            print(f'[sweep] removed {k} exited project containers, {f} networks')
        snapshot()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(launch, jobs))

    snapshot()
    return 0


if __name__ == '__main__':
    sys.exit(main())
