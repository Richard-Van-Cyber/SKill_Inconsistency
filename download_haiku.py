import requests, os, time, json

REPO = 'benchflow/skillsbench-leaderboard'
PREFIX = 'submissions/skillsbench/v1.1/claude-code-with-skills__anthropic-claude-haiku-4-5-20251001-src-paper-v1/2026-01-29__paper-v1-xiangyi-completed-selected3'
BASE_API = f'https://hf-mirror.com/api/datasets/{REPO}/tree/main'
BASE_DL = f'https://hf-mirror.com/datasets/{REPO}/resolve/main'
LOCAL_BASE = '/workspace/skillEvaluation/hf_downloads'

def list_dir(path):
    url = f'{BASE_API}/{path}'
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                print(f'  ERROR listing {path}: {e}')
                return []
            time.sleep(2)

def collect_files(path, all_files):
    items = list_dir(path)
    for item in items:
        if item['type'] == 'file':
            all_files.append(item['path'])
        elif item['type'] == 'directory':
            collect_files(item['path'], all_files)

def download_file(path):
    local_path = os.path.join(LOCAL_BASE, path)
    if os.path.exists(local_path):
        return 'skip'
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    url = f'{BASE_DL}/{path}'
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(r.content)
            return 'ok'
        except Exception as e:
            if attempt == 2:
                print(f'  ERROR downloading {path}: {e}')
                return 'error'
            time.sleep(2)

# Step 1: collect all files
print('Collecting file list...')
all_files = []
collect_files(PREFIX, all_files)
print(f'Total files: {len(all_files)}')

# Step 2: download
ok = skip = error = 0
for i, path in enumerate(all_files):
    result = download_file(path)
    if result == 'ok': ok += 1
    elif result == 'skip': skip += 1
    else: error += 1
    if (i+1) % 50 == 0:
        print(f'  [{i+1}/{len(all_files)}] ok={ok} skip={skip} error={error}')

print(f'\nDone. ok={ok} skip={skip} error={error}')
