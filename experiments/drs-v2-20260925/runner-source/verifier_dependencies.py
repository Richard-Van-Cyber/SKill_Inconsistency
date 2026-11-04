"""Prepare existing verifier requirements after Agent termination, without modifying task outputs."""
import hashlib
import json
import shlex
import time

TASKS = {'fix-druid-loophole-cve', 'fix-erlang-ssh-cve', 'mario-coin-counting', 'grid-dispatch-operator',
         # adversarial-trigger study: these verifiers bootstrap uv from github,
         # which the sandbox cannot reach, so uv/uvx must be injected here.
         'earthquake-plate-calculation', 'earthquake-plate-calculation-adv',
         # downsized DC-OPF instances for the grid Type-1 probe
         'grid-dispatch-small', 'grid-dispatch-small-type1',
         # pddl plan-path probe: its test.sh bootstraps uvx too
         'pddl-tpp-txt', 'pddl-tpp-plan'}

# Extra python packages each verifier needs on top of pytest + pytest-json-ctrf.
# An entry of [] is meaningful: it suppresses the pandas/opencv-python default
# that the original four tasks happen to need.
EXTRA_DEPS = {
    'fix-druid-loophole-cve': ['requests==2.31.0'],
    'fix-erlang-ssh-cve': ['paramiko==3.5.1'],
    'mario-coin-counting': ['pandas', 'opencv-python'],
    'earthquake-plate-calculation': [],
    'earthquake-plate-calculation-adv': [],
}

HASH_SCRIPT = '''import json,hashlib
from pathlib import Path
task=TASK_NAME
if task=='fix-druid-loophole-cve':
 files=[p for p in Path('/root/druid').rglob('*') if p.is_file() and '.git' not in p.parts and p.suffix in ['.java','.xml','.jar']] + [p for p in Path('/root/patches').rglob('*') if p.is_file()]
elif task=='fix-erlang-ssh-cve':
 files=[p for folder in ['src','include'] for p in (Path('/app/workspace/otp_src_27.3.2/lib/ssh')/folder).rglob('*') if p.is_file()]
elif task=='mario-coin-counting':
 files=list(Path('/root').glob('keyframes_*.png'))+[Path('/root/counting_results.csv')]
elif task in ('earthquake-plate-calculation','earthquake-plate-calculation-adv'):
 files=[Path('/root/answer.json')]
else:files=[Path('/root/report.json')]
print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in sorted(set(files))}))
'''


async def prepare_verifier_dependencies(env, root, task_name, out):
    # 47 of the 87 task verifiers bootstrap uv from the network
    # (`curl -LsSf https://astral.sh/uv/... | sh`), which fails intermittently and
    # turns a perfectly good run into verifier_error. Always inject the cached
    # uv/uvx binaries instead of gating on a hardcoded task set.
    async def checked(cmd, timeout=120):
        r = await env.exec(cmd, user='root', timeout_sec=timeout)
        if r.return_code:
            raise RuntimeError('Verifier preparation failed; see verifier-dependency-preparation.log')
        return r
    async def hashes():
        if task_name not in TASKS:
            return {}                      # no artefact guard for unlisted tasks
        code = HASH_SCRIPT.replace('TASK_NAME', repr(task_name))
        return json.loads((await checked('python3 -c ' + shlex.quote(code))).stdout)
    before = await hashes()
    (out/'artifact-hashes-before-verifier-preparation.json').write_text(json.dumps(before, indent=2)+'\n')
    started = time.monotonic()
    await checked('mkdir -p /root/.local/bin')
    binaries = {}
    for name in ['uv', 'uvx']:
        file = root/'.runtime/verifier-cache'/name
        binaries[name] = hashlib.sha256(file.read_bytes()).hexdigest()
        await env.upload_file(file, '/root/.local/bin/'+name)
    await checked('chmod 755 /root/.local/bin/uv /root/.local/bin/uvx; '
                  'printf \'export PATH="/root/.local/bin:$PATH"\\n\' > /root/.local/bin/env')
    if task_name.startswith('pddl-tpp-'):
        prep = shlex.join(['/root/.local/bin/uvx','--with','pytest==8.4.1',
                           '--with','pytest-json-ctrf==0.3.5','--with','numpy==2.4.1',
                           '--with','unified_planning==1.3.0','--with','up-pyperplan==1.1.0',
                           'pytest','--version'])
    elif task_name.startswith('grid-'):
        prep = ('(command -v g++ >/dev/null || (apt-get update && apt-get install -y build-essential)) && '
                '/root/.local/bin/uv pip install --system --break-system-packages pytest pytest-json-ctrf numpy==1.26.4 scipy==1.11.4 cvxpy==1.4.2')
    else:
        deps = EXTRA_DEPS.get(task_name, [])
        prep = shlex.join(['/root/.local/bin/uvx','--with','pytest==8.4.1','--with','pytest-json-ctrf==0.3.5',
                          *[part for dep in deps for part in ['--with',dep]],'pytest','--version'])
    r = await env.exec(prep, user='root', timeout_sec=2400)
    (out/'verifier-dependency-preparation.log').write_text((r.stdout or '')+'\n'+(r.stderr or ''))
    if r.return_code:
        raise RuntimeError('Verifier dependency preparation failed; no task score assigned')
    after = await hashes()
    (out/'artifact-hashes-after-verifier-preparation.json').write_text(json.dumps(after, indent=2)+'\n')
    assert before == after, 'Agent artifacts changed during verifier dependency preparation'
    record = {'applied':True,'phase':'after_agent_before_original_verifier','seconds':round(time.monotonic()-started,2),
              'uv_version':'0.9.7','binary_sha256':binaries,'task_verifier_modified':False,
              'agent_artifact_hashes_unchanged':True,'preparation_command':prep}
    (out/'verifier-dependency-intervention.json').write_text(json.dumps(record,indent=2)+'\n')
    return record
