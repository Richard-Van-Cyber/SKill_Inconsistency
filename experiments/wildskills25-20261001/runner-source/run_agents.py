"""Pilot harness with local-host or SSH task execution.

Credentials are read from stdin or an explicitly configured private file. They
are never included in SSH commands, container environments, or result files.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import math
import os
import random
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    'light': ('gemini', 'gemini-2.5-flash'),
    'medium': ('claude', 'claude-haiku-4-5-20251001'),
    'strong': ('claude', 'claude-opus-4-6'),
}
TOOL = {'type': 'function', 'function': {
    'name': 'run_command',
    'description': 'Run a bash command inside your task Linux container. Each call starts in the task working directory; use cd inside the command when needed. Read and write files, run programs, and install dependencies using this tool.',
    'parameters': {'type': 'object', 'properties': {
        'command': {'type': 'string'},
        'timeout_seconds': {'type': 'integer', 'description': '1 to 300 seconds; default 60.'}
    }, 'required': ['command']}}}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def metadata(task):
    _, header, body = task.joinpath('task.md').read_text().split('---', 2)
    sections = {}
    section = None
    for line in header.splitlines():
        match = re.match(r'^(\w+):\s*$', line)
        if match:
            section = match[1]
            sections[section] = {}
        match = re.match(r'^  (\w+):\s*(.+)$', line)
        if match and section:
            sections[section][match[1]] = match[2].strip("'\"")
    return sections, body.strip()


def skill_index(task):
    rows = []
    for file in sorted(task.glob('environment/skills/*/SKILL.md')):
        text = file.read_text()
        header = text.split('---', 2)[1] if text.startswith('---') else ''
        # Present discovery metadata, not the complete skill instructions.
        rows.append('/app/skills/' + file.parent.name + '/SKILL.md\n' + header.strip())
    return '\n\n'.join(rows)


def image_tag(task):
    digest = hashlib.sha256()
    for path in sorted((task / 'environment').rglob('*')):
        if path.is_file() and path.name != '.DS_Store':
            digest.update(str(path.relative_to(task)).encode())
            digest.update(path.read_bytes())
    return 'anonymous/' + task.name + ':' + digest.hexdigest()[:12]


class Runner:
    def __init__(self, args, keys):
        self.args = args
        self.keys = keys
        self.ssh = None if args.host == 'local' else [
            'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', args.host]
        self.run_id = args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.output = ROOT / 'experiments' / ('agent-' + self.run_id)
        self.output.mkdir(exist_ok=False)
        self.output.joinpath('runner_source.py').write_bytes(Path(__file__).read_bytes())
        self.remote_root = str(ROOT) if args.host == 'local' else self.remote(['pwd'])['stdout'].strip() + '/project'
        self.remote_output = self.remote_root + '/experiments/agent-' + self.run_id
        self.remote(['mkdir', '-p', self.remote_output], check=True)

    def redact(self, text):
        for key in self.keys.values():
            text = text.replace(key, '[REDACTED]')
        return re.sub(r'sk-[A-Za-z0-9_-]{20,}', '[REDACTED]', text)

    def remote(self, argv, timeout=60, check=False):
        command = [str(x) for x in argv]
        if self.ssh is not None:
            command = self.ssh + [shlex.join(command)]
        p = subprocess.run(command,
                           capture_output=True, text=True, timeout=timeout)
        result = {'returncode': p.returncode, 'stdout': self.redact(p.stdout),
                  'stderr': self.redact(p.stderr)}
        if check and p.returncode:
            raise RuntimeError(str(result)[:1500])
        return result

    def api(self, group, payload, timeout):
        request = urllib.request.Request(
            self.args.base_url.rstrip('/') + '/v1/chat/completions',
            data=json.dumps(payload).encode(), headers={
                'Authorization': 'Bearer ' + self.keys[group],
                'Content-Type': 'application/json', 'User-Agent': 'project-agent-experiment/1.0'})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError('API HTTP %d: %s' % (exc.code, self.redact(exc.read().decode(errors='replace'))[:1500])) from None
        except urllib.error.URLError as exc:
            raise RuntimeError('API connection: ' + self.redact(str(exc.reason))) from None

    def run(self, job):
        task, tier = job
        group, model = MODELS[tier]
        name = task.name + '__' + tier
        out = self.output / name
        out.mkdir()
        remote_dir = self.remote_output + '/' + name
        container = 'project-' + self.run_id.lower() + '-' + tier + '-' + task.name
        meta, prompt = metadata(task)
        agent_timeout = int(float(meta['agent']['timeout_sec']))
        verifier_timeout = int(float(meta['verifier']['timeout_sec']))
        result = {'task': task.name, 'model': model, 'tier': tier,
                  'condition': 'OriginalSkill', 'repeat': 1, 'status': 'preparing',
                  'container': container, 'image': image_tag(task), 'score': None,
                  'prompt_tokens': 0, 'completion_tokens': 0, 'api_calls': 0,
                  'tool_calls': 0, 'agent_timeout_seconds': agent_timeout}
        events = out / 'trajectory.jsonl'
        def event(kind, data):
            entry = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'event': kind, 'data': data}
            with events.open('a') as stream:
                stream.write(self.redact(json.dumps(entry, ensure_ascii=False)) + '\n')
        def status():
            dump(out / 'result.json', result)
            print(name, result['status'], 'score=' + str(result['score']), flush=True)
        created = False
        try:
            self.remote(['mkdir', '-p', remote_dir], check=True)
            inspect = self.remote(['docker', 'image', 'inspect', '--format', '{{.Id}}', result['image']])
            if inspect['returncode']:
                result['status'] = 'environment_unavailable'
                status()
                return result
            result['image_id'] = inspect['stdout'].strip()
            self.remote(['docker', 'run', '-d', '--name', container,
                         '--label', 'project.run=' + self.run_id, '--label', 'project.task=' + task.name,
                         '--cpus', meta['sandbox']['cpus'], '--memory', meta['sandbox']['memory_mb'] + 'm',
                         '--pids-limit', '1024', result['image'], 'sleep', str(agent_timeout + verifier_timeout + 600)], check=True)
            created = True
            self.remote(['docker', 'exec', container, 'mkdir', '-p', '/app/skills'], check=True)
            self.remote(['docker', 'cp', self.remote_root + '/selected_tasks/' + task.name + '/environment/skills/.',
                         container + ':/app/skills'], check=True)
            system = ('You are solving a benchmark task in an isolated Linux container. '
                      'Use run_command to inspect files, implement a solution, and validate your outputs. '
                      'Complete the user task and put artifacts at the requested paths. '
                      'You may use the task skills below. Read a relevant SKILL.md before using it; '
                      'resolve its relative paths relative to its own directory. '
                      'Decide whether to use, adapt, or bypass skills based on the task. '
                      'Do not look for reference solutions or benchmark verifiers. '
                      'Do not access external benchmark answers. '
                      'Your final response ends the task.\n\nAvailable skills:\n' + skill_index(task))
            messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]
            event('initial_messages', messages)
            started = time.monotonic()
            deadline = started + agent_timeout
            result['status'] = 'agent_running'
            status()
            for turn in range(self.args.max_turns):
                if time.monotonic() >= deadline:
                    result['agent_end'] = 'timeout'
                    break
                if result['prompt_tokens'] + result['completion_tokens'] >= self.args.total_token_budget or result['completion_tokens'] >= self.args.output_token_budget:
                    result['agent_end'] = 'token_budget'
                    break
                payload = {'model': model, 'messages': messages, 'tools': [TOOL],
                           'temperature': 0.1, 'max_tokens': min(4096, self.args.output_token_budget - result['completion_tokens'])}
                event('api_request', {'turn': turn, 'message_count': len(messages), 'max_tokens': payload['max_tokens']})
                for attempt in range(3):
                    try:
                        response = self.api(group, payload, timeout=max(1, min(180, deadline - time.monotonic())))
                        break
                    except RuntimeError as exc:
                        transient = str(exc).startswith('API connection') or any(
                            str(exc).startswith('API HTTP ' + code) for code in ['429', '500', '502', '503', '504'])
                        event('api_error', {'attempt': attempt + 1, 'error': str(exc), 'usage_unknown': True})
                        result['api_error_attempts'] = result.get('api_error_attempts', 0) + 1
                        if not transient or attempt == 2 or deadline - time.monotonic() < 10:
                            raise
                        time.sleep(2 ** (attempt + 1))
                event('api_response', response)
                result['api_calls'] += 1
                usage = response.get('usage', {})
                result['prompt_tokens'] += int(usage.get('prompt_tokens', 0))
                result['completion_tokens'] += int(usage.get('completion_tokens', 0))
                choices = response.get('choices', [])
                if not choices:
                    raise RuntimeError('API response has no choices')
                message = choices[0]['message']
                messages.append(message)
                calls = message.get('tool_calls') or []
                if not calls:
                    if choices[0].get('finish_reason') == 'length':
                        messages.append({'role': 'user', 'content': 'Your response was truncated. Continue using run_command to complete the task.'})
                        continue
                    result['agent_end'] = 'final_response'
                    dump(out / 'final_response.json', message)
                    break
                for call in calls:
                    result['tool_calls'] += 1
                    try:
                        if call['function']['name'] != 'run_command':
                            raise ValueError('Unknown tool')
                        args = json.loads(call['function']['arguments'])
                        command = args['command']
                        if not isinstance(command, str):
                            raise ValueError('command must be a string')
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError('Agent deadline reached')
                        seconds = max(1, min(300, int(args.get('timeout_seconds', 60)), int(remaining)))
                        event('tool_request', {'id': call['id'], 'command': command, 'timeout_seconds': seconds})
                        output = self.remote(['docker', 'exec', container, 'timeout', '--kill-after=5s',
                                              str(seconds) + 's', 'bash', '-lc', command], timeout=seconds + 30)
                    except (ValueError, KeyError, TypeError, TimeoutError, subprocess.TimeoutExpired) as exc:
                        output = {'tool_error': str(exc)}
                    event('tool_response', {'id': call['id'], 'output': output})
                    content = json.dumps(output, ensure_ascii=False)
                    if len(content) > 24000:
                        content = content[:16000] + '\n[Output truncated; inspect a smaller portion of the file.]\n' + content[-8000:]
                    messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': content})
                dump(out / 'result.json', result)
            else:
                result['agent_end'] = 'turn_limit'
            result['agent_seconds'] = round(time.monotonic() - started, 2)
            result['status'] = 'verifying'
            status()
            # No verifier, expected answer, API key or host directory is visible
            # inside the task container while the model is running.
            event('container_diff', self.remote(['docker', 'diff', container]))
            self.remote(['docker', 'cp', self.remote_root + '/selected_tasks/' + task.name + '/verifier', container + ':/verifier'], check=True)
            self.remote(['docker', 'exec', container, 'bash', '-lc',
                         'mkdir -p /logs/verifier; find /app /root /output -name conftest.py -type f -delete 2>/dev/null; true'], check=True)
            verify = self.remote(['docker', 'exec', container, 'timeout', '--kill-after=10s',
                                  str(verifier_timeout) + 's', 'bash', '/verifier/test.sh'], timeout=verifier_timeout + 45)
            (out / 'verifier.log').write_text(verify['stdout'] + '\n' + verify['stderr'])
            result['verifier_returncode'] = verify['returncode']
            reward = self.remote(['docker', 'exec', container, 'cat', '/logs/verifier/reward.txt'])
            try:
                score = float(reward['stdout'].strip())
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError('Invalid reward')
                result['score'] = score
            except ValueError:
                result['score'] = None
            # Preserve raw reports; infrastructure errors are not agent failures.
            report = self.remote(['docker', 'exec', container, 'cat', '/logs/verifier/ctrf.json'])
            valid_report = False
            if report['returncode'] == 0:
                try:
                    parsed = json.loads(report['stdout'])
                    dump(out / 'ctrf.json', parsed)
                    summary = parsed['results']['summary']
                    result['test_summary'] = summary
                    valid_report = summary.get('tests', 0) > 0 and summary.get('other', 0) == 0
                except (ValueError, KeyError):
                    pass
            elif task.name == 'crystallographic-wyckoff-position-analysis':
                valid_report = result['score'] is not None and verify['returncode'] == 0
            result['status'] = 'graded' if valid_report and result['score'] is not None and verify['returncode'] == 0 else 'verifier_error'
            self.remote(['docker', 'cp', container + ':/logs/verifier', remote_dir + '/verifier'])
        except Exception as exc:
            result['status'] = 'infrastructure_error'
            result['error'] = self.redact(str(exc))[:2000]
            event('error', result['error'])
        finally:
            if created:
                try:
                    self.remote(['docker', 'stop', '--time', '2', container], timeout=40)
                except Exception:
                    pass
            status()
            # Only result files are synchronized; credentials have no file form.
            if self.args.host != 'local':
                sync = subprocess.run(['rsync', '-a', str(out) + '/', self.args.host + ':' + remote_dir + '/'],
                                      capture_output=True, text=True, timeout=120)
                if sync.returncode:
                    result['sync_error'] = self.redact(sync.stderr)[:500]
                    dump(out / 'result.json', result)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='hustserver65')
    parser.add_argument('--base-url', default='https://penguinapi.vip')
    parser.add_argument('--run-id')
    parser.add_argument('--credentials-file', help='Private JSON file; otherwise read credentials from stdin.')
    parser.add_argument('--tasks', nargs='+')
    parser.add_argument('--tiers', nargs='+', choices=list(MODELS), default=list(MODELS))
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--max-turns', type=int, default=60)
    parser.add_argument('--total-token-budget', type=int, default=200000)
    parser.add_argument('--output-token-budget', type=int, default=32768)
    args = parser.parse_args()
    if args.credentials_file:
        credentials_path = Path(args.credentials_file).expanduser()
        stat = credentials_path.stat()
        if stat.st_mode & 0o077 or stat.st_uid != os.getuid():
            raise SystemExit('Credential file must be owned by this user with mode 0600 or stricter.')
        keys = json.loads(credentials_path.read_text())
    else:
        keys = json.load(sys.stdin)
    for tier in args.tiers:
        if MODELS[tier][0] not in keys:
            raise SystemExit('Missing credential group for ' + tier)
    runner = Runner(args, keys)
    tasks = sorted(p for p in (ROOT / 'selected_tasks').iterdir() if p.is_dir())
    if args.tasks:
        if set(args.tasks) - {p.name for p in tasks}:
            raise SystemExit('Unknown task requested')
        tasks = [p for p in tasks if p.name in args.tasks]
    jobs = [(task, tier) for task in tasks for tier in args.tiers]
    random.Random(20260916).shuffle(jobs)
    config = vars(args).copy()
    config.update({'condition': 'OriginalSkill', 'repeats': 1, 'temperature': 0.1,
                   'top_p': 'omitted for cross-provider compatibility',
                   'thinking': 'provider default; record returned usage',
                   'api_location': 'harness host', 'execution_location': args.host,
                   'job_order': [(task.name, tier) for task, tier in jobs]})
    dump(runner.output / 'config.json', config)
    print('Run directory:', runner.output, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(runner.run, jobs))
    dump(runner.output / 'summary.json', results)
    if args.host != 'local':
        subprocess.run(['rsync', '-a', str(runner.output) + '/', args.host + ':' + runner.remote_output + '/'], check=True)
    return int(any(row['status'] != 'graded' for row in results))


if __name__ == '__main__':
    sys.exit(main())
