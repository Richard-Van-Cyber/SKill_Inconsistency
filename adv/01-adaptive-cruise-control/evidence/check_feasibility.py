#!/usr/bin/env python3
"""Is the adversarial lead profile physically achievable at all?

Before blaming a controller we must ask whether ANY controller could keep the gap
above the verifier's 5 m floor. Best-effort controller: track the lead speed but
brake at the -8 m/s^2 limit whenever the gap would otherwise drop below the
16 m headway, i.e. a deliberately conservative reference.
"""
import csv

ADV = 'adv/01-adaptive-cruise-control/data/sensor_data.adv.csv'
SHIPPED = 'tasks/adaptive-cruise-control/environment/sensor_data.csv'
DT = 0.1


def load(path):
    rows = list(csv.DictReader(open(path)))
    out = []
    for r in rows:
        def f(x):
            x = str(x).strip()
            return None if x in ('', 'nan') else float(x)
        out.append((f(r['time']), f(r['lead_speed']), f(r['distance'])))
    return out


def best_effort(prof):
    """Ego starts at 30 m/s at t=30 (end of the speed ramp); ideal braking."""
    ego = 30.0
    min_gap = float('inf')
    for t, lead, dist in prof:
        if lead is None or t is None:
            continue
        if t < 29.99:
            continue
        safe = ego * 1.5 + 10.0
        if dist < safe:
            a = -8.0                      # brake as hard as allowed
        elif ego < lead:
            a = min(3.0, (lead - ego) * 0.5)
        else:
            a = 0.0
        ego = max(0.0, ego + a * DT)
        min_gap = min(min_gap, dist)
    return min_gap


for name, path in (('shipped', SHIPPED), ('adversarial', ADV)):
    prof = load(path)
    tail = [(t, l, d) for t, l, d in prof if t is not None and t >= 25.0]
    # the lead's own trajectory fixes the gap: gap(t) is given by the data until
    # the ego closes it, so the binding question is the minimum tabulated gap.
    tab_min = min((d for t, l, d in tail if d is not None), default=None)
    print(f"{name:12} minimum tabulated gap (t>=25s): {tab_min:.2f} m   "
          f"verifier floor: 5.00 m")
