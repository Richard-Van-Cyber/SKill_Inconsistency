import json, glob, os, time, datetime, statistics

now = time.time()
rows = []
for p in sorted(glob.glob('runs/*/result.json')):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    d['_id'] = os.path.basename(os.path.dirname(p))
    rows.append(d)

def parse(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
    except Exception:
        return None

fin = [(parse(r.get('finished_at')), r) for r in rows]
fin = [(t, r) for t, r in fin if t]
fin.sort()
print(f'now                {datetime.datetime.fromtimestamp(now).strftime("%H:%M:%S")}')
print(f'completed          {len(rows)} / 90')
if fin:
    print(f'first finished     {datetime.datetime.fromtimestamp(fin[0][0]).strftime("%H:%M:%S")}')
    print(f'last finished      {datetime.datetime.fromtimestamp(fin[-1][0]).strftime("%H:%M:%S")}')

walls = sorted(r.get('total_wall_seconds') or 0 for r in rows)
agents = sorted(r.get('agent_seconds') or 0 for r in rows)
if walls:
    print(f'wall seconds/cell  min/med/max = {walls[0]:.0f}/{statistics.median(walls):.0f}/{walls[-1]:.0f}')
    print(f'agent seconds/cell min/med/max = {agents[0]:.0f}/{statistics.median(agents):.0f}/{agents[-1]:.0f}')

# throughput: cells finished in the last windows
def in_window(minutes):
    cut = now - minutes * 60
    return sum(1 for t, _ in fin if t >= cut)

for w in (10, 20, 30):
    c = in_window(w)
    if c:
        print(f'finished last {w:2} min  {c:2}  -> {c/(w/60):.0f} cells/h')

rem = 90 - len(rows)
print()
print(f'remaining          {rem}')

# model A: observed throughput since start
if len(fin) > 1:
    span_h = (fin[-1][0] - fin[0][0]) / 3600
    if span_h > 0.05:
        rate = (len(fin) - 1) / span_h
        eta = now + rem / rate * 3600
        print(f'A. since 1st cell  rate={rate:.1f} cells/h   ETA {datetime.datetime.fromtimestamp(eta).strftime("%H:%M")} (~{rem/rate:.1f}h)')

# model B: recent window
for w in (15, 30):
    c = in_window(w)
    if c >= 3:
        rate = c / (w / 60)
        eta = now + rem / rate * 3600
        print(f'B. last {w:2} min     rate={rate:.1f} cells/h   ETA {datetime.datetime.fromtimestamp(eta).strftime("%H:%M")} (~{rem/rate:.1f}h)')
        break

# model C: median wall time / 2 workers
if walls:
    med = statistics.median(walls)
    rate = 3600 / (med / 2)
    eta = now + rem / rate * 3600
    print(f'C. median wall/2w  rate={rate:.1f} cells/h   ETA {datetime.datetime.fromtimestamp(eta).strftime("%H:%M")} (~{rem/rate:.1f}h)')

print()
print('note: task mix matters -- heavy tasks (pr-review, short-drama, csv-report) '
      'run much longer than the median cell, and they cluster later.')
done_ids = {r['_id'] for r in rows}
heavy = [t for t in ('pr-review-ledger', 'short-drama-asset-audit', 'csv-report-offline', 'keeper-stress-regressions')]
for t in heavy:
    did = sum(1 for i in done_ids if i.startswith(t))
    print(f'  {t:28} {did}/9 done')
