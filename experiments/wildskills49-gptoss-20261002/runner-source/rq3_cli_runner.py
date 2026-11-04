"""Run vendor CLI agents inside native task containers; BenchFlow only provisions and grades.

No custom model/tool execution loop. API relay only injects host-held credentials.
"""
import argparse
import asyncio
import concurrent.futures
import datetime
import hashlib
import importlib.metadata
import json
import os
import random
import shlex
import subprocess
import time
from pathlib import Path

from benchflow.sandbox.docker import DockerSandbox
from benchflow.sandbox.lockdown import setup_sandbox_user, lockdown_paths, harden_before_verify
from benchflow.task.task import Task
from benchflow.task.paths import RolloutPaths
from benchflow.task.verifier import Verifier
from run_agents import ROOT, dump, image_tag
from rq3_cli_proxy import CredentialProxy
from rq3_support import archive_artifacts, audit_usage, tree_hashes
from verifier_dependencies import prepare_verifier_dependencies

CONFIGS = {
    'claude-haiku': {'cli': 'claude', 'group': 'claude', 'model': 'claude-haiku-4-5-20251001', 'version': '2.1.273'},
    'claude-opus': {'cli': 'claude', 'group': 'claude', 'model': 'claude-opus-4-6', 'version': '2.1.273'},
    'deepseek-flash': {'cli': 'claude', 'group': 'deepseek', 'model': 'deepseek-flash', 'version': '2.1.273'},
    'qwen3.6-35b': {'cli': 'claude', 'group': 'ollama', 'model': 'qwen3.6:35b', 'version': '2.1.273'},
    # Local OpenAI open-weight model (MXFP4, 128K ctx) served by the two per-GPU ollama
    # containers; the proxy spreads cells over 11435 (80GB card) and 11436 (40GB card).
    'gpt-oss-20b': {'cli': 'claude', 'group': 'ollama', 'model': 'gpt-oss:20b', 'version': '2.1.273'},
    'codex-gpt55': {'cli': 'codex', 'group': 'gpt', 'model': 'gpt-5.5', 'version': '0.154.0'},
}
MIRRORS = {'PIP_INDEX_URL': 'https://pypi.tuna.tsinghua.edu.cn/simple', 'UV_INDEX_URL': 'https://pypi.tuna.tsinghua.edu.cn/simple'}
# Which conditions inject a task skill package, and which of those take it from
# the study's repaired root rather than the task package itself. This used to be
# an inline `in ['OriginalSkill', 'RepairedSkill']` test; the `DirectedRepairSkill`
# arm added for the directed-repair study therefore fell through it and ran with
# an empty /app/skills while still being labelled a skill arm. Keep the mapping
# explicit here and validate the condition in run_job() so an unknown name fails
# loudly instead of silently degrading to a no-skill run.
# wildskills study: `FixedSkill` is the audited skill package with the doc/script
# inconsistencies repaired (see wildskills/dynamic_eval/fixed_skills/). It is a REPAIRED
# condition, so it is served from the study's inputs/fixed_skills overlay.
SKILL_CONDITIONS = {'OriginalSkill', 'RepairedSkill', 'DirectedRepairSkill', 'FixedSkill'}
REPAIRED_CONDITIONS = {'RepairedSkill', 'DirectedRepairSkill', 'FixedSkill'}
NO_SKILL_CONDITION = 'NoSkill'
KNOWN_CONDITIONS = SKILL_CONDITIONS | {NO_SKILL_CONDITION}
COMMON = ('Complete the task in this isolated benchmark container. Use the installed task skills when relevant; '
          'you may follow, adapt, or bypass them. Put outputs at the requested paths. '
          'Do not seek benchmark reference solutions or hidden verifiers. Work autonomously using local tools. '
          'Do not launch subagents or delegate to other agents.\n\n')
RUNTIME = '/opt/project-official-cli'
PATH = RUNTIME + '/node-v22.23.2-linux-x64/bin:' + RUNTIME + '/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


def release_stopped_networks(session, out):
    """Keep task container files, but release only this finished project's networks."""
    ids = subprocess.check_output(['docker', 'network', 'ls', '-q', '--filter',
                                   'label=com.docker.compose.project=' + session], text=True).split()
    records = []
    for network_id in ids:
        network = json.loads(subprocess.check_output(['docker', 'network', 'inspect', network_id], text=True))[0]
        containers = []
        for cid in network.get('Containers', {}):
            container = json.loads(subprocess.check_output(['docker', 'inspect', cid], text=True))[0]
            if container['State']['Running'] or container['Config'].get('Labels', {}).get('com.docker.compose.project') != session:
                raise RuntimeError('Refusing to release a network with running or foreign containers')
            containers.append(cid)
        records.append(network)
        dump(out / 'released-networks.json', records)
        for cid in containers:
            subprocess.run(['docker', 'network', 'disconnect', network_id, cid], check=True, capture_output=True)
        subprocess.run(['docker', 'network', 'rm', network_id], check=True, capture_output=True)


async def run_job(args, root, keys, job):
    task_path, config_name = job
    conf = CONFIGS[config_name]
    task = Task(task_path)
    out = root / (task_path.name + '__' + config_name)
    if out.exists():
        # An earlier launch was interrupted after creating this directory (e.g. the driver was
        # killed mid-cell). `out.mkdir()` would raise FileExistsError and the cell would be
        # recorded as `crashed` without ever running. Move the stale tree aside instead, so the
        # cell can be re-run while the interrupted attempt is kept for evidence.
        stale = out.with_name(out.name + '.stale-'
                              + datetime.datetime.now().strftime('%Y%m%dT%H%M%S'))
        out.rename(stale)
        print(f'[stale] moved interrupted attempt {out} -> {stale}', flush=True)
    out.mkdir()
    paths = RolloutPaths(out / 'benchflow')
    paths.mkdir()
    api_dir = out / 'api'
    api_dir.mkdir()
    task.config.environment.docker_image = image_tag(task_path)
    session = 'project-' + args.run_id + '-' + task_path.name + '-' + config_name
    env = DockerSandbox(task_path / 'environment', task_path.name, session, paths,
                        task.config.environment, keep_containers=True,
                        mounts_json=[{'type': 'bind', 'source': str(ROOT / '.runtime/official-cli'),
                                      'target': RUNTIME, 'read_only': True}], persistent_env=MIRRORS)
    result = {'task': task_path.name, 'configuration': config_name, **conf,
              'harness': 'Official vendor CLI (native agent loop)', 'orchestrator': 'BenchFlow 0.6.3 sandbox/verifier',
              'condition': 'smoke_check' if args.smoke else args.condition, 'repeat': args.repeat, 'logical_run_id': args.logical_run_id, 'attempt': args.attempt,
              'status': 'preparing', 'score': None, 'container_project': session,
              'image': task.config.environment.docker_image, 'agent_timeout_seconds': 180 if args.smoke else task.config.agent.timeout_sec,
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}

    def status():
        dump(out / 'result.json', result)
        print(out.name, result['status'], 'score=' + str(result.get('score')), flush=True)

    async def checked(cmd, **kwargs):
        r = await env.exec(cmd, **kwargs)
        if r.return_code:
            raise RuntimeError(str(r)[:2000])
        return r

    total_began = time.monotonic()
    proxy = None
    started = False
    phase = 'environment'
    try:
        await env.start(force_build=False)
        started = True
        cid = (await env._run_docker_compose_command(['ps', '-q', 'main'])).stdout.strip()
        result['container_id'] = cid
        result['image_id'] = subprocess.check_output(['docker', 'inspect', '-f', '{{.Image}}', cid], text=True).strip()
        cwd = (await checked('pwd', user='root')).stdout.strip()
        result['workdir'] = cwd
        await setup_sandbox_user(env, 'agent', cwd)
        await checked('mkdir -p /app/skills /output /home/agent/.claude /home/agent/.agents /home/agent/.codex; '
                      'chown -R agent:agent /app/skills /output /home/agent; chmod o+x /root', user='root')
        if not args.smoke and args.condition not in KNOWN_CONDITIONS:
            raise SystemExit(
                f'Unknown condition {args.condition!r}. Refusing to run: an unrecognised condition '
                'injects no skills at all while still being recorded as a skill arm. '
                f'Known conditions: {sorted(KNOWN_CONDITIONS)}')
        skill_source = None
        skills = {}
        if args.condition in SKILL_CONDITIONS:
            skill_source = ((args.repaired_root / task_path.name / 'environment/skills')
                            if args.condition in REPAIRED_CONDITIONS
                            else task_path / 'environment/skills')
            if not skill_source.is_dir():
                raise SystemExit(f'Skill source missing for {args.condition}: {skill_source}')
            skills = tree_hashes(skill_source)
            if not skills:
                raise SystemExit(f'Skill source is empty for {args.condition}: {skill_source}')
            result['skill_source'] = str(skill_source)
            result['skill_source_sha256'] = skills
            await env.upload_dir(skill_source, '/app/skills')
        await checked('chown -R agent:agent /app/skills; ln -sfn /app/skills /home/agent/.claude/skills; '
                      'ln -sfn /app/skills /home/agent/.agents/skills', user='root')
        await lockdown_paths(env, ['/oracle', '/solution', '/verifier', '/tests', '/testbed_verify'])
        # Record what is actually reachable in the container, not what the task
        # package happens to contain: those differ for repaired arms, and reading
        # the task package is what hid the empty-injection bug.
        probe = ("import json;from pathlib import Path;"
                 "print(json.dumps(sorted(str(f.relative_to('/app/skills')) "
                 "for f in Path('/app/skills').rglob('*') if f.is_file())))")
        result['skill_files'] = json.loads((await checked('python3 -c ' + shlex.quote(probe), user='root')).stdout)
        if args.condition in SKILL_CONDITIONS:
            assert sorted(result['skill_files']) == sorted(skills), (
                f'{args.condition} skill injection incomplete: container has '
                f'{sorted(result["skill_files"])}, source has {sorted(skills)}')
        if args.condition == NO_SKILL_CONDITION:
            # Same task image, but no task package is uploaded. Fail before any API call if leaked.
            probe = "import json;from pathlib import Path; roots=[Path('/app/skills'),Path('/home/agent/.claude/skills'),Path('/home/agent/.agents/skills')]; print(json.dumps({str(p):[str(f) for f in p.rglob('*') if f.is_file()] for p in roots}))"
            evidence = json.loads((await checked('python3 -c ' + shlex.quote(probe), user='agent')).stdout)
            assert all(not files for files in evidence.values()), 'NoSkill package isolation failed'
            dump(out / 'skill-isolation.json', {'condition': 'NoSkill', 'task_skill_files': evidence,
                                               'builtin_cli_skills': 'unchanged', 'task_skill_upload': False})
        # local ollama needs no credential; keep it out of the shared secrets file
        proxy = CredentialProxy(keys.get(conf['group'], 'local-no-auth'), conf['group'], conf['model'], api_dir)
        proxy.start()
        vars_ = {**MIRRORS, 'HOME': '/home/agent', 'PATH': PATH, 'CI': 'true', 'NO_COLOR': '1'}
        if conf['cli'] == 'claude':
            vars_.update(ANTHROPIC_BASE_URL=proxy.url, ANTHROPIC_API_KEY='experiment-proxy-placeholder',
                         ANTHROPIC_MODEL=conf['model'], ANTHROPIC_DEFAULT_HAIKU_MODEL=conf['model'],
                         ANTHROPIC_DEFAULT_SONNET_MODEL=conf['model'], ANTHROPIC_DEFAULT_OPUS_MODEL=conf['model'],
                         CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', DISABLE_AUTOUPDATER='1',
                         API_TIMEOUT_MS='180000')
            settings = out / 'claude-settings.json'
            dump(settings, {'env': {'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1'},
                            'permissions': {'deny': ['Agent', 'Task', 'WebSearch', 'WebFetch']}})
            await env.upload_file(settings, '/home/agent/.claude/settings.json')
            cmd = ['claude', '-p', '--model', conf['model'], '--output-format', 'stream-json', '--verbose',
                   '--dangerously-skip-permissions', '--max-turns', '60',
                   '--tools', 'Bash,Read,Write,Edit,Glob,Grep,NotebookEdit,Skill']
        else:
            vars_['FFR2_PROXY_TOKEN'] = 'experiment-proxy-placeholder'
            config = out / 'codex-config.toml'
            config.write_text('model = "gpt-5.5"\nmodel_provider = "penguin"\nmodel_reasoning_effort = "medium"\n'
                              'web_search = "disabled"\n[features]\nmulti_agent = false\n'
                              '[model_providers.penguin]\nname = "Penguin API via credential-only local proxy"\n'
                              f'base_url = "{proxy.url}/v1"\nwire_api = "responses"\nenv_key = "FFR2_PROXY_TOKEN"\n'
                              'request_max_retries = 2\nstream_max_retries = 2\n')
            await env.upload_file(config, '/home/agent/.codex/config.toml')
            cmd = ['codex', 'exec', '--json', '--skip-git-repo-check', '--dangerously-bypass-approvals-and-sandbox', '-']
        prompt = COMMON + task.instruction
        if args.smoke:
            first = sorted(skills)[0].split('/')[1] if skills else next(
                task_path.glob('environment/skills/*/SKILL.md')).parent.name
            prompt = ('This is an installation smoke check, not the benchmark task. '
                      f'Read the installed skill {first} using the native skill mechanism if available. '
                      'Use a shell tool to write exactly official_cli_skill_smoke_ok into /output/cli-smoke.txt. '
                      'Then stop. Do not solve the benchmark or launch subagents.')
        (out / 'prompt.txt').write_text(prompt)
        await env.upload_file(out / 'prompt.txt', '/tmp/project-prompt.txt')
        await checked('chown -R agent:agent /home/agent; chmod 644 /tmp/project-prompt.txt', user='root')
        # Save replay settings with the short-lived relay route redacted.
        dump(out / 'launch.json', {'argv': cmd, 'env': {k: v.replace(proxy.url, '<per-run-credential-proxy>') for k, v in vars_.items()}})
        result['setup_seconds'] = round(time.monotonic() - total_began, 3)
        phase = 'agent'
        result['status'] = 'agent_running'
        status()
        seconds = int(result['agent_timeout_seconds'])
        launch = 'env ' + shlex.join([f'{k}={v}' for k, v in vars_.items()]) + ' ' + shlex.join(cmd)
        command = f'timeout --signal=TERM --kill-after=10s {seconds}s ' + launch + ' < /tmp/project-prompt.txt > /tmp/project-cli.stdout.jsonl 2> /tmp/project-cli.stderr.txt'
        before = time.monotonic()
        r = await env.exec(command, cwd=cwd, user='agent', timeout_sec=seconds + 30)
        result.update(agent_seconds=round(time.monotonic() - before, 2), cli_exit_code=r.return_code,
                      api_calls=proxy.calls, prompt_tokens=proxy.input_tokens, completion_tokens=proxy.output_tokens,
                      observed_models=sorted(proxy.observed_models), budget_stop_reason=proxy.stop_reason)
        await env.download_file('/tmp/project-cli.stdout.jsonl', out / 'cli.stdout.jsonl')
        await env.download_file('/tmp/project-cli.stderr.txt', out / 'cli.stderr.txt')
        stdout_text = (out / 'cli.stdout.jsonl').read_text()
        native_events = []
        for line in stdout_text.splitlines():
            try:
                native_events.append(json.loads(line))
            except ValueError:
                pass
        cli_result = next((e for e in reversed(native_events) if e.get('type') == 'result'), {})
        result['cli_result_subtype'] = cli_result.get('subtype')
        result['native_usage'] = cli_result.get('usage')
        result.update(cli_total_cost_usd=cli_result.get('total_cost_usd'), cli_model_usage=cli_result.get('modelUsage'),
                      cli_duration_ms=cli_result.get('duration_ms'), cli_api_duration_ms=cli_result.get('duration_api_ms'),
                      num_turns=cli_result.get('num_turns'), cli_is_error=cli_result.get('is_error'))
        result['termination_reason'] = ('agent_timeout' if r.return_code in [124, 137] else proxy.stop_reason or cli_result.get('subtype') or 'cli_exit_' + str(r.return_code))
        result['discovered_skills'] = next((e.get('skills') for e in native_events if e.get('subtype') == 'init'), None)
        result['tool_calls'] = sum(len([c for c in e.get('message', {}).get('content', []) if c.get('type') == 'tool_use'])
                                   for e in native_events if e.get('type') == 'assistant') if conf['cli'] == 'claude' else sum(
                                   e.get('type') == 'item.completed' and e.get('item', {}).get('type') in ['command_execution', 'file_change', 'mcp_tool_call'] for e in native_events)
        # Save native session logs before verifier hardening terminates agent-owned processes.
        await env.exec('tar -czf /tmp/project-session.tgz -C /home/agent .claude .codex 2>/dev/null', user='root', timeout_sec=60)
        await env.download_file('/tmp/project-session.tgz', out / 'native-session.tgz')
        proxy.stop()
        proxy_closed = True
        audit_usage(out, result)
        result['agent_artifacts'] = await archive_artifacts(env, task_path.name, out)
        if args.smoke:
            marker = await env.exec('cat /output/cli-smoke.txt', user='root')
            result.update(status='smoke_passed' if r.return_code == 0 and marker.stdout.strip() == 'official_cli_skill_smoke_ok' else 'smoke_failed')
        elif proxy.observed_models != {conf['model']}:
            result.update(status='model_identity_error', error='Returned model differs from requested model; excluded from named-model results.')
        elif proxy.calls == 0 or (r.return_code not in [0, 124] and not proxy.stop_reason and cli_result.get('subtype') != 'error_max_turns'):
            result.update(status='agent_error', error='CLI failed; see native logs. No benchmark score assigned.')
        else:
            phase = 'verifier'
            result['status'] = 'verifying'
            status()
            await harden_before_verify(env, task, sandbox_user='agent', workspace=cwd)
            if args.prepare_verifier_deps:
                result['verifier_dependency_preparation'] = await prepare_verifier_dependencies(env, ROOT, task_path.name, out)
            verifier_began = time.monotonic()
            verified = await asyncio.wait_for(Verifier(task, paths, env).verify(), timeout=task.config.verifier.timeout_sec)
            result['verifier_seconds'] = round(time.monotonic() - verifier_began, 3)
            result['rewards'] = verified.rewards
            result['score'] = (verified.rewards or {}).get('reward', (verified.rewards or {}).get('score'))
            result['status'] = 'graded' if result['score'] is not None else 'verifier_error'
            report = paths.verifier_dir / 'ctrf.json'
            if report.exists():
                result['test_summary'] = json.loads(report.read_text())['results']['summary']
                if not result['test_summary'].get('tests') or result['test_summary'].get('other'):
                    result.update(status='verifier_error', score=None)
            elif task_path.name != 'crystallographic-wyckoff-position-analysis':
                result.update(status='verifier_error', raw_reward=result['score'], score=None,
                              error='Expected CTRF test report is missing; shell fallback reward is not a valid task score.')
    except Exception as exc:
        result.update(status=phase + '_error', score=None, error=str(exc)[:2500])
    finally:
        if proxy and not locals().get('proxy_closed'):
            proxy.stop()
        if started:
            for remote, local in [('/tmp/project-cli.stdout.jsonl', 'cli.stdout.jsonl'), ('/tmp/project-cli.stderr.txt', 'cli.stderr.txt')]:
                if not (out / local).exists():
                    try: await env.download_file(remote, out / local)
                    except Exception: pass
            if not (out / 'native-session.tgz').exists():
                try:
                    await env.exec('tar -czf /tmp/project-session.tgz -C /home/agent .claude .codex 2>/dev/null', user='root', timeout_sec=60)
                    await env.download_file('/tmp/project-session.tgz', out / 'native-session.tgz')
                except Exception as exc: result['session_archive_error'] = str(exc)[:300]
            try:
                await env.stop(delete=False)
                release_stopped_networks(session, out)
            except Exception as exc:
                result['cleanup_error'] = str(exc)[:1000]
        if proxy:
            result.update(api_calls=proxy.calls, prompt_tokens=proxy.input_tokens, completion_tokens=proxy.output_tokens, observed_models=sorted(proxy.observed_models))
            audit_usage(out, result)
        result['total_wall_seconds'] = round(time.monotonic() - total_began, 3)
        result['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        status()
    return result

