import requests, os, time

REPO = 'benchflow/skillsbench-leaderboard'
PREFIX = 'submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3'
BASE_API = f'https://hf-mirror.com/api/datasets/{REPO}/tree/main'
BASE_DL = f'https://hf-mirror.com/datasets/{REPO}/resolve/main'
LOCAL_BASE = '/workspace/skillEvaluation/hf_downloads'

SESS = requests.Session()
SESS.headers.update({'User-Agent': 'Mozilla/5.0'})

def api_list(path, retries=4):
    url = f'{BASE_API}/{path}'
    for i in range(retries):
        try:
            r = SESS.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == retries-1:
                return []
            time.sleep(2 ** i)

def download(path, retries=4):
    local = os.path.join(LOCAL_BASE, path)
    if os.path.exists(local):
        return 'skip'
    os.makedirs(os.path.dirname(local), exist_ok=True)
    url = f'{BASE_DL}/{path}'
    for i in range(retries):
        try:
            r = SESS.get(url, timeout=60)
            r.raise_for_status()
            with open(local, 'wb') as f:
                f.write(r.content)
            return 'ok'
        except Exception as e:
            if i == retries-1:
                print(f'  ERROR {path}: {e}')
                return 'error'
            time.sleep(2 ** i)

# Get trial directories
items = api_list(PREFIX)
trial_dirs = [x['path'] for x in items if x.get('type') == 'directory']
print(f'Found {len(trial_dirs)} trial directories')

ok = skip = error = 0
for i, trial_path in enumerate(trial_dirs):
    # Download claude-code.txt from legacy_agent
    traj_path = f'{trial_path}/trajectory/legacy_agent/claude-code.txt'
    res = download(traj_path)
    if res == 'ok': ok += 1
    elif res == 'skip': skip += 1
    else: error += 1
    time.sleep(0.2)
    if (i+1) % 50 == 0:
        print(f'[{i+1}/{len(trial_dirs)}] ok={ok} skip={skip} error={error}')

print(f'\nDone. ok={ok} skip={skip} error={error}')
