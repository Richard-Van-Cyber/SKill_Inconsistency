#!/usr/bin/env python3
"""Mechanical proof of the save-plan overwrite — no agent, no container, no deps.

Copy of environment/skills/pddl-skills/save_plan.skill:
    def skill(plan, path):
        with open(path, "w") as f: ...text plan...
        with open(path.replace('.txt', '.pkl'), "wb") as f:   # <-- same file if no .txt
            pickle.dump(plan, f)
"""
import os, pickle, tempfile


def skill(plan, path):
    with open(path, "w") as f:
        for action in plan.actions:
            f.write(str(action) + "\n")
    with open(path.replace('.txt', '.pkl'), "wb") as f:
        pickle.dump(plan, f)
    return path


class Plan:
    def __init__(self):
        self.actions = ["drive(truck1, depot1, market1)", "buy(truck1, goods1, market1)"]


with tempfile.TemporaryDirectory() as tmp:
    for name in ('task01.txt', 'task01.plan', 'task01'):
        p = os.path.join(tmp, name)
        skill(Plan(), p)
        head = open(p, 'rb').read(24)
        kind = 'TEXT plan (ok)' if head.startswith(b'drive(') else 'BINARY pickle — text plan DESTROYED'
        print(f"{name:14} {os.path.getsize(p):5} bytes  {kind}")
    print("extra files created:", sorted(f for f in os.listdir(tmp) if f.endswith('.pkl')))
