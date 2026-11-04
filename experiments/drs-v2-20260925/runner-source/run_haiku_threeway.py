"""Frozen 10 x 3 x 3 experiment; native Claude Code with isolated per-run containers."""
import argparse
import asyncio
import concurrent.futures
import datetime
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import subprocess
import threading
from types import SimpleNamespace

from rq3_cli_runner import run_job, ROOT, CONFIGS
from rq3_support import tree_hashes

STUDY = ROOT / 'experiments/haiku45-threeway-20260917'
CONDITIONS = ['NoSkill', 'OriginalSkill', 'RepairedSkill']


def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    lockfile = (STUDY / 'execution.lock').open('w')
    fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert importlib.metadata.version('benchflow') == '0.6.3'
    expected = json.loads((STUDY / 'input-sha256.json').read_text())
    assert tree_hashes(STUDY / 'inputs') == expected, 'Frozen source changed'
    credential = ROOT / '.secrets/penguin.json'
    assert not credential.stat().st_mode & 0o077 and credential.stat().st_uid == os.getuid()
    keys = json.loads(credential.read_text())
    tasks = sorted(p.name for p in (STUDY / 'inputs/selected_tasks').iterdir() if (p / 'task.md').exists())
    assert len(tasks) == 10
    schedule_path = STUDY / 'schedule.json'
    if not schedule_path.exists():
        rng = random.Random(20260917)
        blocks = [(task, rep) for task in tasks for rep in range(1, 4)]
        rng.shuffle(blocks)
        jobs = []
        # Rotate condition order by replicate to balance position within each task.
        task_orders = {}
        for task in tasks:
            order = CONDITIONS.copy(); rng.shuffle(order); task_orders[task] = order
        for task, rep in blocks:
            order = task_orders[task]
            order = order[rep-1:] + order[:rep-1]
            for condition in order:
                jobs.append({'task': task, 'condition': condition, 'repeat': rep,
                             'logical_run_id': task + '__' + condition + '__r' + str(rep)})
        save(schedule_path, jobs)
    jobs = json.loads(schedule_path.read_text())
    assert len(jobs) == len({j['logical_run_id'] for j in jobs}) == 90
    runs = STUDY / 'runs'; runs.mkdir(exist_ok=True)
    runtime = ROOT / '.runtime/official-cli'
    if not (STUDY / 'protocol.json').exists():
        save(STUDY / 'protocol.json', {
            'planned_runs': 90, 'tasks': tasks, 'conditions': CONDITIONS, 'repeats': 3,
            'model': CONFIGS['claude-haiku'], 'workers': args.workers, 'seed': 20260917,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'schedule': 'Randomized task-repeat blocks; Latin rotation of condition position within task',
            'budgets': {'generation_requests': 60, 'cumulative_tokens': 1000000, 'output_tokens': 32768,
                        'agent_timeout': 'unchanged per-task limits', 'check': 'before each API request; last response can overshoot'},
            'retry_policy': 'No performance reruns. Infrastructure failures require inspection; original attempts remain.',
            'verifier_policy': 'Frozen original verifier; ambiguous checks retained and reported separately; infrastructure failures are missing, never zero.',
            'cost_policy': 'Raw token categories plus CLI USD estimate. Actual provider billing unavailable.',
            'sampling': 'Pinned Claude Code defaults; independent fresh sessions; no claimed model seed control',
            'runtime_lock_sha256': hashlib.sha256((runtime / 'package-lock.json').read_bytes()).hexdigest(),
            'prior_runs_included': False,
        })
        (STUDY / 'package-lock.json').write_bytes((runtime / 'package-lock.json').read_bytes())
    sources = ['rq3_cli_runner.py', 'rq3_cli_proxy.py', 'rq3_support.py', 'run_haiku_threeway.py',
               'run_agents.py', 'verifier_dependencies.py']
    source_hashes = {name: hashlib.sha256((ROOT / 'experiments' / name).read_bytes()).hexdigest() for name in sources}
    source_record = STUDY / 'runner-sha256.json'
    if source_record.exists():
        assert json.loads(source_record.read_text()) == source_hashes, 'Runner changed since launch'
    else:
        save(source_record, source_hashes)
        (STUDY / 'runner-source').mkdir(exist_ok=True)
        for name in sources: (STUDY / 'runner-source' / name).write_bytes((ROOT / 'experiments' / name).read_bytes())
    state_lock = threading.Lock()

    def snapshot():
        with state_lock:
            rows = [json.loads(p.read_text()) for p in sorted(runs.glob('*/result.json'))]
            finished = [r for r in rows if r.get('finished_at')]
            save(STUDY / 'summary.json', rows)
            save(STUDY / 'execution-status.json', {
                'status': 'completed' if len(finished) == 90 and all(r['status'] == 'graded' for r in finished)
                          else 'needs_review' if len(finished) == 90 else 'running',
                'planned': 90, 'finished': len(finished), 'graded': sum(r['status'] == 'graded' for r in rows),
                'errors': [{k: r.get(k) for k in ['logical_run_id', 'status', 'error']} for r in finished if r['status'] != 'graded'],
                'recorded_tokens': sum(r.get('total_tokens', 0) for r in rows),
                'cli_estimated_usd': sum(r.get('cli_total_cost_usd') or 0 for r in rows),
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'pid': os.getpid()})

    def launch(job):
        out = runs / job['logical_run_id']
        if out.exists():
            return  # Never overwrite a completed or interrupted attempt.
        out.mkdir()
        ordinal = jobs.index(job) + 1
        settings = SimpleNamespace(run_id='h45-20260917-' + str(ordinal), condition=job['condition'],
            repeat=job['repeat'], logical_run_id=job['logical_run_id'], attempt=1, smoke=False,
            repaired_root=STUDY / 'inputs/fixed_skills', prepare_verifier_deps=True)
        # run_job uses task/config child directories; retain them for full provenance.
        r = asyncio.run(run_job(settings, out, keys, (STUDY / 'inputs/selected_tasks' / job['task'], 'claude-haiku')))
        save(out / 'result.json', r)
        snapshot()

    # A real RepairedSkill task is the smoke/pilot; counts as its planned cell.
    pilot = next(j for j in jobs if j['task'] == 'dialogue-parser' and j['condition'] == 'RepairedSkill' and j['repeat'] == 1)
    launch(pilot)
    p = json.loads((runs / pilot['logical_run_id'] / 'result.json').read_text())
    assert p['status'] == 'graded' and p.get('observed_models') == [CONFIGS['claude-haiku']['model']], 'Pilot requires inspection'
    assert p.get('discovered_skills') and p.get('total_tokens', 0) > 0, 'Pilot skill/usage capture failed'
    snapshot()
    if args.pilot: return
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(launch, jobs))
    snapshot()
    subprocess.run([os.sys.executable, str(ROOT / 'experiments/analyze_haiku_threeway.py')], check=True)


if __name__ == '__main__': main()
