import json, glob, os, collections, statistics

rows = []
for p in sorted(glob.glob('runs/*/result.json')):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    d['_id'] = os.path.basename(os.path.dirname(p))
    rows.append(d)

arms = ('NoSkill', 'OriginalSkill', 'FixedSkill')
by = collections.defaultdict(list)
for r in rows:
    by[r['task']].append(r)

def med(v):
    return statistics.median(v) if v else float('nan')

print(f'completed cells: {len(rows)}')
print()
hdr = f'{"task":28} {"n":>3} {"calls med":>9} {"calls min-max":>13} {"turns med":>9} {"tok med":>9} {"calls by arm (med)":>26}'
print(hdr)
print('-' * len(hdr))
for t in sorted(by):
    v = by[t]
    calls = [r.get('api_calls') or 0 for r in v]
    turns = [r.get('num_turns') or 0 for r in v]
    toks = [r.get('total_tokens') or 0 for r in v]
    per_arm = []
    for a in arms:
        c = [r.get('api_calls') or 0 for r in v if r['condition'] == a]
        per_arm.append(f'{a[:3]}={med(c):.0f}' if c else f'{a[:3]}=-')
    print(f'{t:28} {len(v):3} {med(calls):9.0f} {f"{min(calls)}-{max(calls)}":>13} '
          f'{med(turns):9.0f} {med(toks):9,.0f} {"  ".join(per_arm):>26}')

print()
allc = [r.get('api_calls') or 0 for r in rows]
allt = [r.get('num_turns') or 0 for r in rows]
print(f'overall calls  min/med/mean/max = {min(allc)}/{med(allc):.0f}/{sum(allc)/len(allc):.1f}/{max(allc)}   (cap 60)')
print(f'overall turns  min/med/mean/max = {min(allt)}/{med(allt):.0f}/{sum(allt)/len(allt):.1f}/{max(allt)}')
print()
print('distribution of api_calls:')
buckets = collections.Counter()
for c in allc:
    if c <= 5: buckets['1-5'] += 1
    elif c <= 10: buckets['6-10'] += 1
    elif c <= 15: buckets['11-15'] += 1
    elif c <= 20: buckets['16-20'] += 1
    elif c <= 30: buckets['21-30'] += 1
    else: buckets['31-60'] += 1
for k in ('1-5', '6-10', '11-15', '16-20', '21-30', '31-60'):
    if buckets[k]:
        print(f'  {k:>6}: {buckets[k]:2}  {"#" * buckets[k]}')
print()
print('cells that reached the 60-request cap:',
      sum(1 for c in allc if c >= 60))
