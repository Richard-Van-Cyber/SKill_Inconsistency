#!/usr/bin/env python3
"""Build the single-arm study inputs, deploy them, then run 30 cells.

Two roles in one file, selected by the flags:

  client (has ssh access)   build inputs -> rsync to server -> start scheduler
  server (runs the cells)   --serve, reads only SERVER_REPO paths

What the client does:
  1. Copy the primary study's inputs/selected_tasks (never modified).
  2. Overlay the workspace <CLIENT_REPO>/fixed_skills as inputs/fixed_skills.
  3. Freeze input-sha256.json and write protocol.json / schedule.json /
     runner-sha256.json / package-lock.json for the new study.
  4. rsync the study to <SERVER_REPO>/experiments/<STUDY_NAME> and run it there.

Safety properties:
  * The primary study directory is never written to.
  * An existing cell directory is never overwritten (run_job refuses), so a
    re-run resumes instead of repeating.
  * input-sha256.json is written once; later runs verify it and refuse to run if
    the inputs changed.

Usage:
    python3 runner-source/run_directed_repair.py --deploy-only
    python3 runner-source/run_directed_repair.py --pilot
    python3 runner-source/run_directed_repair.py
    python3 runner-source/run_directed_repair.py --host 10.0.0.65
"""
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

import directed_repair_config as CFG  # noqa: E402

# rq3_cli_runner imports benchflow, which is only installed on the server. The
# client only needs `--check-server`, the study build and rsync, so those
# imports are deferred to the code paths that actually run cells.
def asyncio_run(coro):
    """Run a coroutine to completion from a worker thread."""
    import asyncio
    return asyncio.run(coro)


def _load_run_job():
    from rq3_cli_runner import run_job
    return run_job


def _tree_hashes(root):
    from rq3_support import tree_hashes
    return tree_hashes(root)

SKILLS_ENTRY = 'fixed_skills'


class StudyPaths:
    """One path model, two roles.

    client: builds inputs/metadata under CLIENT_REPO and rsyncs them over.
    server: owns runs/, summary.json and execution-status.json under SERVER_REPO.

    There are no cross-mounts, so the role is decided by which study directory
    actually exists: while building on the client, the server path does not
    exist; on the server it does.
    """

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
    def client_study(self):
        return Path(CFG.CLIENT_EXPERIMENTS) / CFG.STUDY_NAME


dirs = StudyPaths()
STUDY = dirs.study
DEPLOY_TARGET = f'{CFG.SERVER_EXPERIMENTS}/{CFG.STUDY_NAME}'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    tmp.replace(path)


def load(path):
    return json.loads(path.read_text())


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_fixed_skills():
    path = Path(CFG.CLIENT_FIXED_SKILLS)
    if not path.is_dir():
        raise SystemExit(f'Missing workspace skill package: {path}')
    return path


def task_names(primary_inputs):
    tasks = sorted(p.name for p in (primary_inputs / 'selected_tasks').iterdir()
                   if (p / 'task.md').exists())
    if len(tasks) != 10:
        raise SystemExit(f'Expected 10 tasks, found {len(tasks)}: {tasks}')
    return tasks


def build_inputs():
    """Create the new study's frozen input tree on the client. Idempotent."""
    # Prefer the frozen inputs that already live in the primary study directory
    # (they are hash-verified below via the frozen manifest); fall back to the
    # configured location so the same script works from a clean checkout too.
    candidates = [Path(CFG.CLIENT_STUDY_INPUTS) if hasattr(CFG, 'CLIENT_STUDY_INPUTS') else None,
                  Path(CFG.CLIENT_PRIMARY_INPUTS)]
    primary_inputs = next((c for c in candidates if c and c.is_dir()), None)
    if primary_inputs is None:
        raise SystemExit(
            'Primary study inputs not found. Looked in:\n  ' +
            '\n  '.join(str(c) for c in candidates if c) +
            f'\nFetch them once with:\n'
            f'  rsync -a {CFG.SERVER_HOST}:{CFG.SERVER_PRIMARY_INPUTS}/ '
            f'{CFG.CLIENT_PRIMARY_INPUTS}/')
    print(f'[ok] input source: {primary_inputs}')
    tasks = task_names(primary_inputs)
    inputs = dirs.client_study / 'inputs'

    (inputs / 'selected_tasks').mkdir(parents=True, exist_ok=True)
    # Mirror the primary task packages (task.md, environment/, verifier/, oracle/).
    subprocess.run(['rsync', '-a', '--delete',
                    str(primary_inputs / 'selected_tasks') + '/',
                    str(inputs / 'selected_tasks') + '/'], check=True)

    # Upload the freshly repaired skills from the workspace.
    skills_src = workspace_fixed_skills()
    subprocess.run(['rsync', '-a', '--delete',
                    str(skills_src) + '/', str(inputs / SKILLS_ENTRY) + '/'], check=True)

    missing = [t for t in tasks if not (inputs / SKILLS_ENTRY / t / 'environment/skills').is_dir()]
    if missing:
        raise SystemExit(f'Workspace skill package missing tasks: {missing}')

    # court-form-filling was never modified: assert it is byte-identical to the
    # original package so it can keep serving as the no-intervention control.
    import filecmp
    cmp = filecmp.dircmp(str(inputs / 'selected_tasks/court-form-filling/environment/skills'),
                         str(inputs / SKILLS_ENTRY / 'court-form-filling/environment/skills'))
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        print('[warn] court-form-filling differs from the original package:',
              cmp.left_only, cmp.right_only, cmp.diff_files)
    else:
        print('[ok] court-form-filling is byte-identical to the original package (control intact)')

    record = dirs.study / 'input-sha256.json'
    hashes = _tree_hashes(inputs)
    if record.exists():
        if load(record) != hashes:
            raise SystemExit(
                'inputs/ changed but input-sha256.json already exists. The new study is '
                'frozen; build a fresh study directory instead of editing this one.')
        print(f'[ok] inputs hash verified ({len(hashes)} files)')
    else:
        save(record, hashes)
        print(f'[ok] froze inputs ({len(hashes)} files) -> {record}')
    return tasks, hashes


def build_metadata(tasks, hashes):
    """protocol.json, schedule.json, runner-sha256.json, package-lock.json.

    Written on the client and rsynced to the server, so every path recorded here
    is a server path.
    """
    runtime = dirs.repo / '.runtime/official-cli'
    protocol = dirs.study / 'protocol.json'
    if not protocol.exists():
        save(protocol, {
            'planned_runs': len(tasks) * CFG.REPEATS,
            'tasks': tasks,
            'conditions': [CFG.CONDITION],
            'repeats': CFG.REPEATS,
            'arm_meaning': ('DirectedRepairSkill = workspace fixed_skills after the '
                            'evidence-driven repair pass; NOT the 2026-09-17 repaired package'),
            'skill_source': SKILLS_ENTRY,
            'benchflow_version': CFG.EXPECTED_BENCHFLOW_VERSION,
            'model': CFG.MODEL_CONFIG_NAME,
            'workers': CFG.WORKERS,
            'seed': CFG.SEED,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'budgets': {
                'generation_requests': CFG.BUDGET_GENERATION_REQUESTS,
                'cumulative_tokens': CFG.BUDGET_CUMULATIVE_TOKENS,
                'output_tokens': CFG.BUDGET_OUTPUT_TOKENS,
                'scope': 'per run, enforced by the per-run credential proxy',
                'budget_matched_to_primary_study': CFG.BUDGET_MATCHED_TO_PRIMARY_STUDY,
                'primary_study_values': [60, 1_000_000, 32_768],
                'note': ('budget-matched with the primary study NoSkill / OriginalSkill '
                         'arms, so this arm is directly comparable with them'
                         if CFG.BUDGET_MATCHED_TO_PRIMARY_STUDY else
                         'raised relative to the primary study, whose 60/1M/32K cap '
                         'truncated 23 of 90 runs; NOT budget-matched, so it is only '
                         'comparable with another study that also raises the budget'),
            },
            'retry_policy': 'Infrastructure failures require inspection; cells are never overwritten.',
            'prior_runs_included': False,
            'primary_study': CFG.SERVER_EXPERIMENTS + '/' + CFG.PRIMARY_STUDY_NAME,
            'selected_tasks_source': CFG.SERVER_PRIMARY_INPUTS + '/selected_tasks',
        })
        print(f'[ok] protocol.json -> {protocol}')

    schedule = dirs.study / 'schedule.json'
    if not schedule.exists():
        rng = random.Random(CFG.SEED)
        blocks = [(task, rep) for task in tasks for rep in range(1, CFG.REPEATS + 1)]
        rng.shuffle(blocks)
        jobs = [{'task': task, 'condition': CFG.CONDITION, 'repeat': rep,
                 'logical_run_id': f'{task}__{CFG.CONDITION}__r{rep}'}
                for task, rep in blocks]
        save(schedule, jobs)
        print(f'[ok] schedule.json ({len(jobs)} cells) -> {schedule}')
    jobs = load(schedule)
    ids = {j['logical_run_id'] for j in jobs}
    if len(jobs) != len(ids) != len(tasks) * CFG.REPEATS:
        raise SystemExit('schedule.json is inconsistent with tasks x repeats')
    if {j['condition'] for j in jobs} != {CFG.CONDITION}:
        raise SystemExit('schedule.json contains a condition this study must not run')

    runner_record = dirs.study / 'runner-sha256.json'
    sources = ['rq3_cli_runner.py', 'rq3_cli_proxy.py', 'rq3_support.py',
               'run_directed_repair.py', 'directed_repair_config.py',
               'run_agents.py', 'verifier_dependencies.py']
    # rq3_cli_proxy.py is patched at runtime (budget values only); record the
    # original file's hash plus the patch description so the change is auditable.
    source_hashes = {name: sha256_file(HERE / name) for name in sources}
    source_hashes['_patched_and_verified'] = {
        'target': 'rq3_cli_proxy.py',
        'what': ('module-level budget constants drive the per-request budget check '
                 f"({CFG.BUDGET_GENERATION_REQUESTS}/"
                 f"{CFG.BUDGET_CUMULATIVE_TOKENS}/"
                 f"{CFG.BUDGET_OUTPUT_TOKENS}); the check reads those constants "
                 'instead of literals. No routing, credential or '
                 'usage-accounting change.'),
        'primary_study_values': [60, 1_000_000, 32_768],
        'budget_matched_to_primary_study': CFG.BUDGET_MATCHED_TO_PRIMARY_STUDY,
        'verified_by': 'run_directed_repair.verify_proxy_budget',
    }
    if runner_record.exists():
        previous = load(runner_record)
        if previous != source_hashes:
            raise SystemExit('Runner sources changed since this study was created; '
                             'create a new study directory instead.')
        print('[ok] runner-sha256.json verified')
    else:
        save(runner_record, source_hashes)
        print(f'[ok] runner-sha256.json -> {runner_record}')

    lock = dirs.study / 'package-lock.json'
    if not lock.exists() and (runtime / 'package-lock.json').exists():
        lock.write_bytes((runtime / 'package-lock.json').read_bytes())
    return jobs


def verify_proxy_budget():
    """rq3_cli_proxy.py carries the raised per-run budget; verify before running.

    The proxy is the enforcement point for the per-run API budget, so this is
    checked rather than assumed. Routing, credential handling and usage parsing
    in that file are byte-identical to the primary study apart from the three
    constants (see runner-sha256.json['_patched_and_verified']).
    """
    import rq3_cli_proxy

    actual = (rq3_cli_proxy.API_BUDGET_GENERATION_REQUESTS,
              rq3_cli_proxy.API_BUDGET_CUMULATIVE_TOKENS,
              rq3_cli_proxy.API_BUDGET_OUTPUT_TOKENS)
    expected = (CFG.BUDGET_GENERATION_REQUESTS,
                CFG.BUDGET_CUMULATIVE_TOKENS,
                CFG.BUDGET_OUTPUT_TOKENS)
    if actual != expected:
        raise SystemExit(f'Proxy budget mismatch: file has {actual}, config wants {expected}')
    print(f'[ok] proxy budget = {actual[0]} requests / {actual[1]:,} tokens / {actual[2]:,} output tokens (per run)')


def preflight(host):
    """Fail fast if the server or the credential file is not reachable."""
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host]
    probe = subprocess.run(ssh + ['bash -lc "hostname; python3 -V"'],
                           capture_output=True, text=True)
    if probe.returncode:
        raise SystemExit(f'Cannot reach {host} over ssh:\n{probe.stderr.strip()}')
    print(f'[ok] ssh {host}: {probe.stdout.strip().splitlines()[:1]}')
    docker = subprocess.run(ssh + ['bash -lc "docker version --format \'{{.Server.Version}}\'"'],
                            capture_output=True, text=True)
    if docker.returncode:
        raise SystemExit(f'Docker not usable on {host}:\n{docker.stderr.strip()}')
    print(f'[ok] docker server {docker.stdout.strip()}')
    # Credentials are host-held; read them over ssh and hand them to run_job as
    # an in-memory dict, exactly like the primary study did.
    cred_path = f'{CFG.SERVER_REPO}/.secrets/penguin.json'
    perms = subprocess.run(ssh + [f'stat -c "%a %u" {shlex.quote(cred_path)}'],
                           capture_output=True, text=True)
    if perms.returncode:
        raise SystemExit(f'Missing credential file on {host}: {cred_path}')
    mode, uid = perms.stdout.split()
    # stat prints octal; parse it as such (int("600") is 600 decimal, whose
    # low bits spuriously look like group/other permissions).
    if int(mode, 8) & 0o077:
        raise SystemExit(f'Credential file mode too open on {host}: {mode} (must be 0600/0400)')
    keys_raw = subprocess.run(ssh + [f'cat {shlex.quote(cred_path)}'],
                              capture_output=True, text=True)
    if keys_raw.returncode:
        raise SystemExit(f'Cannot read credentials on {host}')
    keys = json.loads(keys_raw.stdout)
    if CFG.MODEL_CONFIG_NAME.split('-')[0] not in keys and 'claude' not in keys:
        raise SystemExit(f'Credential groups present: {sorted(keys)}')
    print(f'[ok] credentials loaded from {host} (mode {mode}, groups {sorted(keys)})')
    return keys


def server_check(host: str, study: str = "") -> int:
    """Read-only audit of everything the experiment needs on the server.

    Every item is checked with a remote command; nothing is written except a
    probe file that is removed again. Exit status is the number of failed
    checks, so it doubles as a gate for CI or a manual runbook.
    """
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host]
    # The runtime and verifier cache are mounted from *inside the study
    # directory* (rq3_cli_runner uses ROOT / '.runtime/...' where ROOT is the
    # study dir), so the check must look there — looking at <repo>/.runtime
    # silently passed while the container had no CLI at all.
    study_dir = f'{CFG.SERVER_EXPERIMENTS}/{study or CFG.STUDY_NAME}'

    def run(cmd: str) -> tuple[int, str]:
        r = subprocess.run(ssh + [cmd], capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()

    results: list[tuple[bool, str, str]] = []

    def check(name: str, cmd: str, hint: str) -> None:
        code, out = run(cmd)
        ok = code == 0
        results.append((ok, name, "" if ok else f"{out[:160] or 'failed'} | 建议: {hint}"))

    check("ssh 可达", 'hostname', f'ssh {host} 需要免密登录（BatchMode）')
    check("仓库目录存在", f'test -d {shlex.quote(CFG.SERVER_REPO)}',
          f'在 {host} 上创建 {CFG.SERVER_REPO} 并放入 experiments/、.runtime/、.secrets/')
    check("benchflow 0.6.3", f'{shlex.quote(CFG.SERVER_REPO + "/.venv-benchflow/bin/python")} '
          f'-c "import importlib.metadata as m; assert m.version(\'benchflow\')==\'{CFG.EXPECTED_BENCHFLOW_VERSION}\'"',
          f'python3 -m venv {CFG.SERVER_REPO}/.venv-benchflow && '
          f'{CFG.SERVER_REPO}/.venv-benchflow/bin/pip install benchflow=={CFG.EXPECTED_BENCHFLOW_VERSION}')
    cred = f'{CFG.SERVER_REPO}/.secrets/penguin.json'
    check(f"凭据文件 {cred}", f'test -r {shlex.quote(cred)}',
          '放置 {"claude": "<api key>"} 形式的 JSON')
    check("凭据权限 0600 或更严", f'test "$(stat -c %a {shlex.quote(cred)})" = 600',
          f'chmod 600 {cred}')
    check("凭据含 claude 分组",
          f'{shlex.quote(CFG.SERVER_REPO + "/.venv-benchflow/bin/python")} -c '
          f'"import json;assert \'claude\' in json.load(open(\'{cred}\'))"',
          'JSON 里需要 claude 字段（Haiku 走这个分组）')
    runtime = f'{study_dir}/.runtime/official-cli'
    check(f"CLI 运行时 {runtime}", f'test -x {shlex.quote(runtime + "/node-v22.23.2-linux-x64/bin/node")}',
          '放入 Node v22.23.2 与 node_modules（含 @anthropic-ai/claude-code）')
    check("CLI 可执行且版本 2.1.273",
          f'{shlex.quote(runtime + "/node_modules/.bin/claude")} --version 2>&1 | grep -q 2.1.273',
          '运行时里的 claude 必须是可执行的原生二进制（npm 的 bin 指向 claude.exe，'
          '需要从官方 CDN 覆盖为 linux-x64 二进制）')
    check("verifier 依赖缓存 uv/uvx",
          f'test -x {shlex.quote(study_dir + "/.runtime/verifier-cache/uv")} '
          f'-a -x {shlex.quote(study_dir + "/.runtime/verifier-cache/uvx")}',
          '放置 uv 与 uvx 静态二进制（verifier 准备阶段直接读这两个文件）')
    check("docker 可用", 'docker version --format "{{.Server.Version}}"', '启动 docker daemon')
    check("docker 镜像已构建（anonymous/*）",
          'test "$(docker images --format \'{{.Repository}}\' | grep -c \'^anonymous/\')" -ge 10',
          '每个任务的环境镜像必须预先构建（runner 用 force_build=False，缺镜像会直接 environment_error）')
    check("docker bridge 可用于代理", 'ip -4 addr show docker0 2>/dev/null | grep -q 172.17.0.1',
          'CredentialProxy 绑定 172.17.0.1，需要默认 bridge 网络')
    check("可访问上游 API", 'curl -sS -o /dev/null -w "%{http_code}" --max-time 10 '
          'https://penguinapi.vip/v1/messages -X POST -H "content-type: application/json" -d "{}" '
          '| grep -qE "401|400"',
          '上游需可达（返回 401/400 即算通；超时或 5xx 说明上游不可用）')

    width = max(len(n) for _, n, _ in results)
    print(f'\n服务器体检: {host}\n' + '-' * (width + 12))
    for ok, name, detail in results:
        print(f'  [{"ok  " if ok else "FAIL"}] {name:<{width}}  {detail}')
    failed = sum(1 for ok, _, _ in results if not ok)
    print('-' * (width + 12))
    print(f'  {len(results) - failed}/{len(results)} 项通过' + ('' if not failed else f'，{failed} 项待处理'))
    return failed


def deploy(host):
    """Push this study's runner sources + frozen inputs to the server."""
    ssh = ['ssh', '-o', 'BatchMode=yes', host]
    remote_study = DEPLOY_TARGET
    subprocess.run(ssh + [f'mkdir -p {shlex.quote(remote_study)}/runner-source'], check=True)
    for name in ['rq3_cli_runner.py', 'rq3_cli_proxy.py', 'rq3_support.py', 'run_agents.py',
                 'verifier_dependencies.py', 'run_directed_repair.py',
                 'directed_repair_config.py']:
        subprocess.run(['rsync', '-a', str(HERE / name),
                        f'{host}:{remote_study}/runner-source/{name}'], check=True)
    subprocess.run(['rsync', '-a', '--exclude', 'runs/',
                    str(dirs.client_study) + '/', f'{host}:{remote_study}/'], check=True)
    subprocess.run(ssh + [f'mkdir -p {shlex.quote(CFG.SERVER_EXPERIMENTS)}'], check=True)
    print(f'[ok] deployed -> {host}:{remote_study}')


def verify_frozen_inputs():
    """Refuse to run if inputs/ no longer matches the recorded freeze."""
    record = dirs.study / 'input-sha256.json'
    if not record.exists():
        raise SystemExit(f'Missing {record}; run the client build step first.')
    actual = _tree_hashes(dirs.inputs)
    expected = load(record)
    if actual != expected:
        changed = sorted(set(actual) ^ set(expected)) or [
            k for k in expected if actual.get(k) != expected[k]]
        raise SystemExit(f'Frozen inputs changed: {changed[:5]} (+{max(0, len(changed)-5)} more)')
    print(f'[ok] frozen inputs verified ({len(actual)} files)')


def install_proxy_defaults_from_env():
    """Let the scheduler override budgets via env without editing sources.

    rq3_cli_proxy already carries the raised constants; this only reports them
    and allows an explicit env override for a future study.
    """
    import rq3_cli_proxy

    mapping = {
        'API_BUDGET_GENERATION_REQUESTS': 'DIRECTED_REPAIR_MAX_REQUESTS',
        'API_BUDGET_CUMULATIVE_TOKENS': 'DIRECTED_REPAIR_MAX_TOKENS',
        'API_BUDGET_OUTPUT_TOKENS': 'DIRECTED_REPAIR_MAX_OUTPUT_TOKENS',
    }
    applied = {}
    for attr, env in mapping.items():
        if env in os.environ:
            setattr(rq3_cli_proxy, attr, int(os.environ[env]))
        applied[attr] = getattr(rq3_cli_proxy, attr)
    print(f'[ok] per-run budget: {applied}')
    return applied


def check_environment():
    import importlib.metadata
    version = importlib.metadata.version('benchflow')
    if version != CFG.EXPECTED_BENCHFLOW_VERSION:
        raise SystemExit(f'benchflow {version} != expected {CFG.EXPECTED_BENCHFLOW_VERSION}')


def serve(args):
    """Server role: run the schedule that the client already deployed."""
    check_environment()
    # The scheduler must serve the study directory that owns this script. Without
    # this check a missing DR_STUDY_NAME silently serves whatever the default
    # study is -- and against the wrong budget.
    script_study = HERE.parent.resolve()
    if Path(dirs.study).resolve() != script_study:
        raise SystemExit(
            f'serve() runs from {script_study} but dirs.study={Path(dirs.study).resolve()}.\n'
            f'  Set DR_STUDY_NAME={script_study.name!r} (and the matching '
            'DIRECTED_REPAIR_MAX_* budget) before launching.')
    verify_frozen_inputs()
    install_proxy_defaults_from_env()
    jobs = load(dirs.study / 'schedule.json')
    tasks = load(dirs.study / 'protocol.json')['tasks']
    if sorted({j['task'] for j in jobs}) != sorted(tasks):
        raise SystemExit('schedule.json tasks != protocol.json tasks')
    if {j['condition'] for j in jobs} != {CFG.CONDITION}:
        raise SystemExit('schedule.json contains a condition this study must not run')
    # Credentials stay on the server; read them here rather than transferring them.
    cred = Path(CFG.SERVER_REPO) / '.secrets/penguin.json'
    mode = cred.stat().st_mode
    if mode & 0o077:
        raise SystemExit(f'Credential file mode too open: {oct(mode)}')
    keys = json.loads(cred.read_text())
    print(f'[serve] study={CFG.STUDY_NAME} role={dirs.role} cells={len(jobs)} '
          f'workers={args.workers} condition={CFG.CONDITION}')
    run_jobs(jobs, keys, args)


def ready_tasks(host: str) -> set[str]:
    """Task names whose image already exists on the server.

    Building all images takes a while; cells whose image is missing fail fast
    with environment_error, so it is useful to know which tasks can start now.
    """
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host]
    r = subprocess.run(
        ssh + ['docker images --format "{{.Repository}}:{{.Tag}}" | grep "^anonymous/" || true'],
        capture_output=True, text=True)
    if r.returncode:
        return set()
    out = set()
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith('anonymous/'):
            out.add(line[len('anonymous/'):].rsplit(':', 1)[0])
    return out


def run_jobs(jobs, keys, args):
    runs = dirs.study / 'runs'
    runs.mkdir(exist_ok=True)
    state_lock = threading.Lock()

    def snapshot():
        with state_lock:
            rows = [json.loads(p.read_text()) for p in sorted(runs.glob('*/result.json'))]
            finished = [r for r in rows if r.get('finished_at')]
            save(dirs.study / 'summary.json', rows)
            save(dirs.study / 'execution-status.json', {
                'status': ('completed' if len(finished) == len(jobs)
                           and all(r['status'] == 'graded' for r in finished)
                           else 'needs_review' if len(finished) == len(jobs) else 'running'),
                'study': CFG.STUDY_NAME, 'condition': CFG.CONDITION, 'role': dirs.role,
                'planned': len(jobs), 'finished': len(finished),
                'graded': sum(r['status'] == 'graded' for r in rows),
                'errors': [{k: r.get(k) for k in ('logical_run_id', 'status', 'error')}
                           for r in finished if r['status'] != 'graded'],
                'recorded_tokens': sum(r.get('total_tokens', 0) for r in rows),
                'cli_estimated_usd': sum(r.get('cli_total_cost_usd') or 0 for r in rows),
                'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'pid': os.getpid()})

    def launch(job):
        out = runs / job['logical_run_id']
        if out.exists():
            return
        out.mkdir()
        ordinal = jobs.index(job) + 1
        settings = SimpleNamespace(
            run_id='dr-20260922-' + str(ordinal), condition=CFG.CONDITION,
            repeat=job['repeat'], logical_run_id=job['logical_run_id'], attempt=1,
            smoke=False,
            # This study's arm is the skill package frozen under its own inputs/.
            repaired_root=dirs.inputs / SKILLS_ENTRY,
            prepare_verifier_deps=True)
        r = asyncio_run(_load_run_job()(settings, out, keys,
                                (dirs.inputs / 'selected_tasks' / job['task'],
                                 CFG.MODEL_CONFIG_NAME)))
        save(out / 'result.json', r)
        snapshot()

    # One real cell acts as the pilot: it must be graded and report the expected
    # model, otherwise the study stops for inspection. Which cell that is can be
    # chosen with --pilot-task, and defaults to the first cell whose image is
    # already built on the server (so a run can start while other images build).
    if getattr(args, 'skip_pilot', False):
        print('[pilot] skipped (--skip-pilot)')
        pilot = None
    else:
        # Only consider cells this run will actually execute: picking a cell
        # outside --cells made the pilot fail on a not-yet-built image and
        # aborted the whole batch.
        scope = list(jobs)
        if getattr(args, 'cells', None):
            wanted_ids = set(args.cells)
            scoped = [j for j in jobs if j['logical_run_id'] in wanted_ids]
            if scoped:
                scope = scoped
        wanted = getattr(args, 'pilot_task', None)
        if wanted:
            pilot = next((j for j in scope if j['task'] == wanted), None)
            if pilot is None:
                raise SystemExit(f'--pilot-task {wanted} is not in this schedule')
            # prefer a cell of that task that has not run yet
            pilot = next((j for j in scope if j['task'] == wanted
                          and not (runs / j['logical_run_id']).exists()), pilot)
        else:
            ready = ready_tasks(args.host) if not getattr(args, 'serve', False) else None
            if ready is None:
                import json as _json
                ready = set(_json.loads((dirs.study / 'protocol.json').read_text())['tasks'])
            pilot = next((j for j in scope if j['task'] in ready), scope[0])
            if pilot['task'] not in ready:
                print(f'[pilot] WARNING: no image ready for {pilot["task"]}; '
                      f'pilot will likely fail with environment_error')
        if pilot is not None and not (runs / pilot['logical_run_id']).exists():
            print(f'[pilot] {pilot["logical_run_id"]}')
            launch(pilot)
            p = load(runs / pilot['logical_run_id'] / 'result.json')
            if p.get('status') != 'graded' or not p.get('observed_models'):
                raise SystemExit(
                    f'Pilot needs inspection: status={p.get("status")} error={p.get("error")}\n'
                    f'  (use --skip-pilot to proceed anyway, e.g. while images are still building)')
            snapshot()
    if getattr(args, 'pilot', False):
        print('pilot complete')
        return 0

    targets = jobs
    if getattr(args, 'cells', None):
        wanted = set(args.cells)
        targets = [j for j in jobs if j['logical_run_id'] in wanted]
        if not targets:
            raise SystemExit('no cells matched --cells')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(launch, targets))
    snapshot()
    print(f'finished; status -> {dirs.study / "execution-status.json"}')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default=CFG.SERVER_HOST)
    ap.add_argument('--workers', type=int, default=CFG.WORKERS)
    ap.add_argument('--study', default=CFG.STUDY_NAME, help='study directory name to check/serve')
    ap.add_argument('--check-server', action='store_true',
                    help='server role: read-only audit of prerequisites, then exit')
    ap.add_argument('--serve', action='store_true',
                    help='server role: run the deployed schedule (no building, no rsync)')
    ap.add_argument('--deploy-only', action='store_true')
    ap.add_argument('--skip-deploy', action='store_true')
    ap.add_argument('--pilot', action='store_true', help='run only the pilot cell')
    ap.add_argument('--pilot-task', default=None,
                    help='use a cell of this task as the pilot (default: first task whose image exists)')
    ap.add_argument('--skip-pilot', action='store_true',
                    help='do not run a pilot before the batch (use while images are still building)')
    ap.add_argument('--cells', nargs='*', help='run only these logical_run_ids')
    args = ap.parse_args()

    if args.check_server:
        return server_check(args.host, args.study)
    if args.serve:
        return serve(args)

    # Client role: build locally, verify, deploy, then start the server scheduler.
    keys = preflight(args.host)
    # Apply the env budget override BEFORE verifying, so a budget-matched study
    # verifies against the override it will actually run with.
    install_proxy_defaults_from_env()
    tasks, hashes = build_inputs()
    jobs = build_metadata(tasks, hashes)
    verify_proxy_budget()
    if not args.skip_deploy:
        deploy(args.host)
    if args.deploy_only:
        print('deploy-only: inputs and sources are on the server; stopping here')
        return 0

    extra = ''
    if args.pilot:
        extra += ' --pilot'
    if args.skip_pilot:
        extra += ' --skip-pilot'
    if args.pilot_task:
        extra += ' --pilot-task ' + shlex.quote(args.pilot_task)
    # --cells must reach the server: the scheduler runs there and reads its own
    # argv, so a client-side-only filter silently runs the whole schedule.
    if args.cells:
        extra += ' --cells ' + ' '.join(shlex.quote(c) for c in args.cells)
    remote_cmd = (f'cd {shlex.quote(CFG.SERVER_REPO)} && '
                  f'{shlex.quote(CFG.SERVER_REPO + "/.venv-benchflow/bin/python")} -u '
                  f'{shlex.quote(DEPLOY_TARGET + "/runner-source/run_directed_repair.py")} '
                  f'--serve --workers {args.workers}{extra} '
                  f'> {shlex.quote(DEPLOY_TARGET + "/batch.log")} 2>&1')
    print(f'[serve] {remote_cmd}')
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', args.host, remote_cmd])
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
