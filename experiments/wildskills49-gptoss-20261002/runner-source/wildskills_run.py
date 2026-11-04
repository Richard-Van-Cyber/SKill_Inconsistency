#!/usr/bin/env python3
"""Client/server driver for the wildskills dynamic-evaluation study.

Client role (run from this Mac):

    python3 runner-source/wildskills_run.py --check-server
    python3 runner-source/wildskills_run.py --dry-run
    python3 runner-source/wildskills_run.py --build-images --deploy-only
    python3 runner-source/wildskills_run.py --arms OriginalSkill --cells spring-http-requests__OriginalSkill__r1

Server role (started by the client over ssh):

    <study>/runner-source/wildskills_run.py --serve

The heavy lifting (container start, vendor CLI, verifier) is done by
`rq3_cli_runner.run_job`, the same runner the primary three-arm study used, so the cells are
directly comparable with it.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import random
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import wildskills_config as CFG  # noqa: E402

SKILLS_ENTRY = 'fixed_skills'


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(path)


def load(path):
    return json.loads(path.read_text())


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.name != '.DS_Store'}


class Paths:
    def __init__(self):
        server_study = Path(CFG.SERVER_EXPERIMENTS) / CFG.STUDY_NAME
        if server_study.is_dir():
            self.role, self.repo, self.study = 'server', Path(CFG.SERVER_REPO), server_study
        else:
            self.role = 'client'
            self.repo = Path(CFG.CLIENT_REPO)
            self.study = Path(CFG.CLIENT_EXPERIMENTS) / CFG.STUDY_NAME

    @property
    def inputs(self):
        return self.study / 'inputs'

    @property
    def runs(self):
        return self.study / 'runs'


DIRS = Paths()
STUDY = DIRS.study
DEPLOY_TARGET = f'{CFG.SERVER_EXPERIMENTS}/{CFG.STUDY_NAME}'


# --------------------------------------------------------------------------------------
# client: build the frozen study inputs
# --------------------------------------------------------------------------------------
def build_inputs():
    inputs = DIRS.study / 'inputs'
    (inputs / 'selected_tasks').mkdir(parents=True, exist_ok=True)
    (inputs / SKILLS_ENTRY).mkdir(parents=True, exist_ok=True)

    for task in CFG.TASKS:
        src = Path(CFG.CLIENT_TASK_SOURCE) / task
        if not (src / 'task.md').exists():
            raise SystemExit(f'missing task package: {src}')
        subprocess.run(['rsync', '-a', '--delete',
                        str(src) + '/', str(inputs / 'selected_tasks' / task) + '/'], check=True)
        fixed = Path(CFG.CLIENT_FIXED_SKILLS) / task
        if not (fixed / 'environment/skills').is_dir():
            raise SystemExit(f'missing repaired skill overlay: {fixed}')
        subprocess.run(['rsync', '-a', '--delete',
                        str(fixed) + '/', str(inputs / SKILLS_ENTRY / task) + '/'], check=True)

    # .DS_Store would be excluded from the image hash but still shipped; drop it.
    for junk in list(inputs.rglob('.DS_Store')):
        junk.unlink()

    record = DIRS.study / 'input-sha256.json'
    hashes = tree_hashes(inputs)
    if record.exists():
        if load(record) != hashes:
            raise SystemExit('inputs/ changed but input-sha256.json already exists; '
                             'create a new study directory instead of editing this one')
        print(f'[ok] inputs hash verified ({len(hashes)} files)')
    else:
        save(record, hashes)
        print(f'[ok] froze inputs ({len(hashes)} files)')
    return hashes


def build_metadata(hashes):
    protocol = DIRS.study / 'protocol.json'
    if not protocol.exists():
        save(protocol, {
            'study': CFG.STUDY_NAME,
            'purpose': ('dynamically measure the impact of audited skill inconsistencies: '
                        'the verifier executes the artifact the agent produced'),
            'planned_runs': len(CFG.TASKS) * len(CFG.CONDITIONS) * CFG.REPEATS,
            'tasks': CFG.TASKS,
            'conditions': CFG.CONDITIONS,
            'repeats': CFG.REPEATS,
            'model': CFG.MODEL_CONFIG_NAME,
            'workers': CFG.WORKERS,
            'seed': CFG.SEED,
            'benchflow_version': CFG.EXPECTED_BENCHFLOW_VERSION,
            'budgets': {'generation_requests': CFG.BUDGET_GENERATION_REQUESTS,
                        'cumulative_tokens': CFG.BUDGET_CUMULATIVE_TOKENS,
                        'output_tokens': CFG.BUDGET_OUTPUT_TOKENS,
                        'scope': 'per run, enforced by the per-run credential proxy'},
            'task_source': CFG.CLIENT_TASK_SOURCE,
            'fixed_skill_source': CFG.CLIENT_FIXED_SKILLS,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        print('[ok] protocol.json')

    schedule = DIRS.study / 'schedule.json'
    if not schedule.exists():
        jobs = [{'task': task, 'condition': condition, 'repeat': repeat,
                 'logical_run_id': f'{task}__{condition}__r{repeat}'}
                for task in CFG.TASKS
                for condition in CFG.CONDITIONS
                for repeat in range(1, CFG.REPEATS + 1)]
        random.Random(CFG.SEED).shuffle(jobs)
        save(schedule, jobs)
        print(f'[ok] schedule.json ({len(jobs)} cells)')
    jobs = load(schedule)
    if {j['condition'] for j in jobs} - set(CFG.CONDITIONS):
        raise SystemExit('schedule.json contains a condition this study must not run')
    return jobs


def verify_frozen_inputs():
    record = DIRS.study / 'input-sha256.json'
    if not record.exists():
        raise SystemExit(f'missing {record}')
    actual = tree_hashes(DIRS.inputs)
    expected = load(record)
    if actual != expected:
        changed = sorted(set(actual) ^ set(expected)) or [k for k in expected
                                                          if actual.get(k) != expected[k]]
        raise SystemExit(f'frozen inputs changed: {changed[:5]}')
    print(f'[ok] frozen inputs verified ({len(actual)} files)')


def verify_proxy_budget():
    import rq3_cli_proxy
    actual = (rq3_cli_proxy.API_BUDGET_GENERATION_REQUESTS,
              rq3_cli_proxy.API_BUDGET_CUMULATIVE_TOKENS,
              rq3_cli_proxy.API_BUDGET_OUTPUT_TOKENS)
    expected = (CFG.BUDGET_GENERATION_REQUESTS, CFG.BUDGET_CUMULATIVE_TOKENS,
                CFG.BUDGET_OUTPUT_TOKENS)
    if actual != expected:
        raise SystemExit(f'proxy budget mismatch: file={actual} config={expected}')
    print(f'[ok] per-run budget {actual[0]} requests / {actual[1]:,} tokens / {actual[2]:,} output')


# --------------------------------------------------------------------------------------
# client: server prerequisites, image build, deploy
# --------------------------------------------------------------------------------------
def ssh_prefix(host):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', host]


def remote(host, command, timeout=600, check=True):
    result = subprocess.run(ssh_prefix(host) + [command], capture_output=True,
                            text=True, timeout=timeout)
    if check and result.returncode:
        raise SystemExit(f'remote command failed: {command}\n{result.stdout}\n{result.stderr}')
    return result


def preflight(host):
    probe = remote(host, 'hostname; docker version --format "{{.Server.Version}}"', check=False)
    if probe.returncode:
        raise SystemExit(f'cannot reach {host}: {probe.stderr.strip()}')
    print(f'[ok] ssh+docker: {probe.stdout.strip().splitlines()}')

    cred = f'{CFG.SERVER_REPO}/.secrets/penguin.json'
    perms = remote(host, f'stat -c "%a" {shlex.quote(cred)}', check=False)
    if perms.returncode:
        raise SystemExit(f'missing credential file {cred}')
    if int(perms.stdout.strip(), 8) & 0o077:
        raise SystemExit(f'credential file too open: {perms.stdout.strip()}')
    print(f'[ok] credentials present (mode {perms.stdout.strip()})')

    runtime = CFG.SERVER_RUNTIME_SOURCE
    cli = runtime + '/official-cli'
    check = remote(host, f'test -x {shlex.quote(cli + "/node-v22.23.2-linux-x64/bin/node")} '
                         f'-a -x {shlex.quote(cli + "/node_modules/.bin/claude")} '
                         f'-a -x {shlex.quote(runtime + "/verifier-cache/uv")}', check=False)
    if check.returncode:
        raise SystemExit(f'official CLI runtime incomplete at {cli}')
    version = remote(host, f'PATH={shlex.quote(cli + "/node-v22.23.2-linux-x64/bin")}:$PATH '
                           f'{shlex.quote(cli + "/node_modules/.bin/claude")} --version',
                     check=False)
    reported = (version.stdout.strip() or version.stderr.strip())[:120]
    print(f'[ok] runtime cli: {reported}')
    if '2.1.273' not in reported:
        raise SystemExit('runtime claude is not 2.1.273; the study would not be comparable')


def image_tags():
    sys.path.insert(0, str(HERE))
    from run_agents import image_tag
    return {task: image_tag(Path(CFG.CLIENT_TASK_SOURCE) / task) for task in CFG.TASKS}


def build_images(host):
    tags = image_tags()
    for task, tag in tags.items():
        exists = remote(host, f'docker image inspect {shlex.quote(tag)} >/dev/null 2>&1', check=False)
        if exists.returncode == 0:
            print(f'[skip] image present: {tag}')
            continue
        context = f'{DEPLOY_TARGET}/inputs/selected_tasks/{task}/environment'
        print(f'[build] {task} -> {tag}')
        result = remote(host, f'docker build -t {shlex.quote(tag)} {shlex.quote(context)}',
                        timeout=1800, check=False)
        if result.returncode:
            raise SystemExit(f'image build failed for {task}:\n{result.stdout[-3000:]}\n'
                             f'{result.stderr[-3000:]}')
    return tags


def deploy(host):
    remote(host, f'mkdir -p {shlex.quote(DEPLOY_TARGET)}/runner-source')
    for name in ['rq3_cli_runner.py', 'rq3_cli_proxy.py', 'rq3_support.py', 'run_agents.py',
                 'verifier_dependencies.py', 'wildskills_run.py', 'wildskills_config.py']:
        subprocess.run(['rsync', '-a', str(HERE / name),
                        f'{host}:{DEPLOY_TARGET}/runner-source/{name}'], check=True)
    subprocess.run(['rsync', '-a', '--exclude', 'runs/', '--exclude', '.DS_Store',
                    str(DIRS.study) + '/', f'{host}:{DEPLOY_TARGET}/'], check=True)
    # The CLI runtime and the verifier cache are mounted from inside the study directory.
    remote(host, f'ln -sfn {shlex.quote(CFG.SERVER_RUNTIME_SOURCE)} '
                 f'{shlex.quote(DEPLOY_TARGET + "/.runtime")}')
    print(f'[ok] deployed -> {host}:{DEPLOY_TARGET}')


# --------------------------------------------------------------------------------------
# server: run the schedule
# --------------------------------------------------------------------------------------
def check_environment():
    import importlib.metadata
    version = importlib.metadata.version('benchflow')
    if version != CFG.EXPECTED_BENCHFLOW_VERSION:
        raise SystemExit(f'benchflow {version} != {CFG.EXPECTED_BENCHFLOW_VERSION}')


def serve(args):
    check_environment()
    verify_frozen_inputs()
    import rq3_cli_proxy
    rq3_cli_proxy.API_BUDGET_GENERATION_REQUESTS = CFG.BUDGET_GENERATION_REQUESTS
    rq3_cli_proxy.API_BUDGET_CUMULATIVE_TOKENS = CFG.BUDGET_CUMULATIVE_TOKENS
    rq3_cli_proxy.API_BUDGET_OUTPUT_TOKENS = CFG.BUDGET_OUTPUT_TOKENS
    print(f'[serve] per-run budget {CFG.BUDGET_GENERATION_REQUESTS}/'
          f'{CFG.BUDGET_CUMULATIVE_TOKENS}/{CFG.BUDGET_OUTPUT_TOKENS}')

    from rq3_cli_runner import run_job

    jobs = load(DIRS.study / 'schedule.json')
    if args.arms:
        wanted = {a.strip() for a in args.arms.split(',') if a.strip()}
        unknown = wanted - set(CFG.CONDITIONS)
        if unknown:
            raise SystemExit(f'--arms: unknown {sorted(unknown)}')
        jobs = [j for j in jobs if j['condition'] in wanted]
    if args.cells:
        wanted = {c.strip() for c in args.cells.split(',') if c.strip()}
        jobs = [j for j in jobs if j['logical_run_id'] in wanted]
        if not jobs:
            raise SystemExit('--cells matched nothing')

    cred = Path(CFG.SERVER_REPO) / '.secrets/penguin.json'
    if cred.stat().st_mode & 0o077:
        raise SystemExit('credential file mode too open')
    keys = json.loads(cred.read_text())

    runs = DIRS.runs
    runs.mkdir(exist_ok=True)
    superseded = DIRS.study / 'runs_superseded'
    lock = threading.Lock()
    done = [0]

    def sweep_docker():
        """Release the previous batch's containers and networks.

        `rq3_cli_runner` keeps the task containers after `env.stop(delete=False)` for evidence,
        but Docker's default address pool runs out after roughly 30 project networks, after
        which every later cell dies with "all predefined address pools have been fully
        subnetted" -> environment_error. Only our own `anonymous/` images are ever touched.
        """
        try:
            ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'status=exited'],
                                          text=True).split()
        except Exception:
            return 0, 0
        killed = 0
        for cid in ids:
            try:
                image = subprocess.check_output(
                    ['docker', 'inspect', '-f', '{{.Config.Image}}', cid], text=True).strip()
            except Exception:
                continue
            if image.startswith('anonymous/'):
                subprocess.run(['docker', 'rm', '-f', cid], capture_output=True)
                killed += 1
        names = subprocess.run(['docker', 'network', 'ls', '--format', '{{.Name}}'],
                               capture_output=True, text=True).stdout.split()
        freed = 0
        for name in names:
            if name.startswith('project-') and subprocess.run(
                    ['docker', 'network', 'rm', name], capture_output=True).returncode == 0:
                freed += 1
        print(f'[sweep] removed {killed} exited project containers, {freed} networks', flush=True)
        return killed, freed

    def snapshot():
        with lock:
            rows = []
            for path in sorted(runs.glob('*/result.json')):
                try:
                    rows.append(json.loads(path.read_text()))
                except Exception:
                    pass
            save(DIRS.study / 'summary.json', rows)
            finished = [r for r in rows if r.get('finished_at')]
            save(DIRS.study / 'execution-status.json', {
                'status': 'completed' if len(finished) >= len(jobs) else 'running',
                'planned': len(jobs), 'finished': len(finished),
                'graded': sum(1 for r in rows if r.get('status') == 'graded'),
                'errors': [{'logical_run_id': r.get('logical_run_id'), 'status': r.get('status'),
                            'error': r.get('error')}
                           for r in finished if r.get('status') != 'graded'],
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

    def launch(job):
        out = runs / job['logical_run_id']
        if (out / 'result.json').exists():
            previous = json.loads((out / 'result.json').read_text())
            if previous.get('status') == 'graded':
                print(f'[skip] {job["logical_run_id"]}', flush=True)
                return
            # A non-graded cell is retried, but its evidence is kept rather than deleted.
            target = superseded / (job['logical_run_id'] + '__' + datetime.datetime.now(
                datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
            target.parent.mkdir(parents=True, exist_ok=True)
            out.rename(target)
            print(f'[retry] {job["logical_run_id"]} (previous status '
                  f'{previous.get("status")}, kept at {target.name})', flush=True)
        out.mkdir(parents=True, exist_ok=True)
        settings = SimpleNamespace(
            run_id='ws-' + job['logical_run_id'].replace('__', '-'),
            condition=job['condition'], repeat=job['repeat'],
            logical_run_id=job['logical_run_id'], attempt=1, smoke=False,
            repaired_root=DIRS.inputs / SKILLS_ENTRY,
            prepare_verifier_deps=False)
        task_path = DIRS.inputs / 'selected_tasks' / job['task']
        try:
            result = asyncio_run(run_job(settings, out, keys, (task_path, CFG.MODEL_CONFIG_NAME)))
        except Exception as exc:  # noqa: BLE001
            import traceback
            result = {'logical_run_id': job['logical_run_id'], 'status': 'crashed',
                      'error': f'{type(exc).__name__}: {exc}',
                      'traceback': traceback.format_exc()[-1500:]}
        result['arm'] = job['condition']
        save(out / 'result.json', result)
        print(f'[done] {job["logical_run_id"]} status={result.get("status")} '
              f'score={result.get("score")}', flush=True)
        with lock:
            done[0] += 1
            sweep_now = done[0] % 2 == 0
        if sweep_now:
            sweep_docker()
        snapshot()

    print(f'[serve] study={CFG.STUDY_NAME} role={DIRS.role} cells={len(jobs)} '
          f'workers={args.workers}')
    sweep_docker()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(launch, jobs))
    sweep_docker()
    snapshot()
    return 0


# --------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default=CFG.SERVER_HOST)
    ap.add_argument('--workers', type=int, default=CFG.WORKERS)
    ap.add_argument('--arms', default='', help='comma separated subset of the conditions')
    ap.add_argument('--cells', default='', help='comma separated logical_run_ids')
    ap.add_argument('--serve', action='store_true')
    ap.add_argument('--check-server', action='store_true')
    ap.add_argument('--build-images', action='store_true')
    ap.add_argument('--deploy-only', action='store_true')
    ap.add_argument('--skip-deploy', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if args.serve:
        return serve(args)

    if args.check_server:
        preflight(args.host)
        return 0

    verify_proxy_budget()
    build_inputs()
    jobs = build_metadata(tree_hashes(DIRS.inputs))
    for job in jobs:
        print('  cell', job['logical_run_id'])
    if args.dry_run:
        print('[dry-run] inputs built, nothing deployed')
        return 0

    preflight(args.host)
    if not args.skip_deploy:
        deploy(args.host)
    build_images(args.host)
    if args.deploy_only:
        print('[ok] deploy-only: study and images are on the server')
        return 0

    extra = ''
    if args.arms:
        extra += ' --arms ' + shlex.quote(args.arms)
    if args.cells:
        extra += ' --cells ' + shlex.quote(args.cells)
    # The server process re-imports wildskills_config, so the study identity and the task list
    # must travel with the command. Without this the scheduler falls back to the default study
    # name and silently serves whatever schedule lives there.
    # WS_MODEL must travel too: the server re-imports wildskills_config, so without it the
    # scheduler would fall back to the default model and silently run the wrong axis.
    env_prefix = (f'WS_STUDY_NAME={shlex.quote(CFG.STUDY_NAME)} '
                  f'WS_TASKS={shlex.quote(",".join(CFG.TASKS))} '
                  f'WS_REPEATS={CFG.REPEATS} '
                  f'WS_MODEL={shlex.quote(CFG.MODEL_CONFIG_NAME)} ')
    remote_cmd = (f'cd {shlex.quote(CFG.SERVER_REPO)} && {env_prefix}'
                  f'{shlex.quote(CFG.SERVER_REPO + "/.venv-benchflow/bin/python")} -u '
                  f'{shlex.quote(DEPLOY_TARGET + "/runner-source/wildskills_run.py")} '
                  f'--serve --workers {args.workers}{extra} '
                  f'> {shlex.quote(DEPLOY_TARGET + "/batch.log")} 2>&1')
    print(f'[serve] {remote_cmd}')
    result = subprocess.run(ssh_prefix(args.host) + [remote_cmd])
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
