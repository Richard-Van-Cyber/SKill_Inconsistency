import json, glob, collections, os, statistics

rows = []
for p in sorted(glob.glob('runs/*/result.json')):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    d['_id'] = os.path.basename(os.path.dirname(p))
    rows.append(d)

arms = ('NoSkill', 'OriginalSkill', 'FixedSkill')
by = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    by[r['task']][r['condition']].append(r)

w = 17
print('per task x arm -- mean(score) over completed trials')
print('task'.ljust(28) + ''.join(a.rjust(w) for a in arms))
for t in sorted(by):
    line = t.ljust(28)
    for a in arms:
        v = by[t].get(a) or []
        if not v:
            line += '-'.rjust(w)
            continue
        sc = [x['score'] for x in v if x.get('score') is not None]
        mean = sum(sc) / len(sc) if sc else float('nan')
        trunc = sum(1 for x in v if (x.get('budget_stop_reason') or '') == 'api_budget')
        mark = f'{mean:.3f} (n={len(v)}' + (f',{trunc}T)' if trunc else ')')
        line += mark.rjust(w)
    print(line)

print()
print('arm means (cell weighted over completed trials)')
for a in arms:
    sc = [r['score'] for r in rows if r['condition'] == a and r.get('score') is not None]
    if sc:
        print(f'  {a:14} n={len(sc):2} mean={sum(sc)/len(sc):.4f}')
allsc = [r['score'] for r in rows if r.get('score') is not None]
print(f'  {"ALL":14} n={len(allsc):2} mean={sum(allsc)/len(allsc):.4f}')

print()
print('problem cells (non-graded):')
bad = [r for r in rows if r.get('status') != 'graded']
print('  none' if not bad else '')
for r in bad:
    print(f"  {r['_id']:52} status={r.get('status')}")

print()
print('observed models:', dict(collections.Counter(
    m for r in rows for m in (r.get('observed_models') or []))))
tk = [r.get('total_tokens') or 0 for r in rows]
print(f'tokens med={statistics.median(tk):,.0f}  max={max(tk):,}')
