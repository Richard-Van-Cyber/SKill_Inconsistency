#!/usr/bin/env python3
"""Mechanical proof: the `alloc` helper the skill tells the agent to copy
silently drops lb / ub / integer.

SKILL.md "Variable Map Pattern" section, verbatim:

    def alloc(name, shape, lb=0.0, ub=float("inf"), integer=False):
        global n
        size = int(np.prod(shape))
        idx = np.arange(n, n + size).reshape(shape)
        offset[name] = idx
        n += size
        return idx

    u = alloc("commitment", (G, T), lb=0, ub=1, integer=True)
    start = alloc("startup", (G, T), lb=0, ub=1, integer=True)
    dispatch = alloc("dispatch", (G, T), lb=0)

We rebuild a 2-generator / 3-period unit-commitment relaxation exactly the way the
documented pattern invites, and compare it against the same model built with the
bounds/integrality the call site *asked* for.
"""
import os
import re

import numpy as np
from scipy.optimize import linprog

SKILL = ('tasks/energy-unit-commitment/environment/skills/'
         'milp-solver-workflow/SKILL.md')


def load_documented_helper(path=SKILL):
    """Extract the `alloc` definition straight out of the shipped SKILL.md.

    Nothing is hand-copied: if the document changes, this proof changes with it.
    """
    text = open(path, encoding='utf-8').read()
    block = re.search(r'```python\n(.*?)```', text, re.S).group(1)
    fn = re.search(r'def alloc\(.*?\n(?=\n|u = alloc)', block, re.S).group(0)
    calls = re.findall(r'^(u|start|dispatch|reserve) = alloc\(.*\)$', block, re.M)
    ns = {'np': np, 'n': 0, 'offset': {}}
    exec(fn, ns)
    return fn, ns['alloc'], calls


ALLOC_SRC, alloc, CALL_SITES = load_documented_helper()
print("=== the helper exactly as SKILL.md ships it ===")
print(ALLOC_SRC.rstrip())
print("call sites found in the same block:", CALL_SITES)
print()
print("does the body ever mention lb / ub / integer? ->",
      bool(re.search(r'\b(lb|ub|integer)\b', ALLOC_SRC.split('):', 1)[1])))
print()

offset = {}
n = 0


def build(honour_bounds: bool):
    # fresh namespace per build: `alloc` keeps its counter there, exactly as the
    # documented module-level `n`/`offset` would in the agent's own script
    ns = {'np': np, 'n': 0, 'offset': {}}
    exec(ALLOC_SRC, ns)
    alloc_ = ns['alloc']
    G, T = 2, 3
    u = alloc_("commitment", (G, T), lb=0, ub=1, integer=True)
    p = alloc_("dispatch", (G, T), lb=0)
    n = ns['n']

    pmin = np.array([20.0, 30.0])
    pmax = np.array([100.0, 100.0])
    cost = np.array([10.0, 40.0])          # $/MWh
    dem = np.array([50.0, 120.0, 50.0])    # MW

    nv = n
    c = np.zeros(nv)
    for g in range(G):
        for t in range(T):
            c[p[g, t]] = cost[g]

    A_eq, b_eq = [], []
    for t in range(T):                      # demand balance
        row = np.zeros(nv)
        for g in range(G):
            row[p[g, t]] = 1.0
        A_eq.append(row); b_eq.append(dem[t])

    A_ub, b_ub = [], []
    for g in range(G):
        for t in range(T):
            r = np.zeros(nv); r[p[g, t]] = 1.0; r[u[g, t]] = -pmax[g]
            A_ub.append(r); b_ub.append(0.0)                 # p <= pmax*u
            r = np.zeros(nv); r[p[g, t]] = -1.0; r[u[g, t]] = pmin[g]
            A_ub.append(r); b_ub.append(0.0)                 # p >= pmin*u
    if not honour_bounds:
        # what the documented alloc actually registers: NOTHING.
        bounds = [(0.0, None)] * nv
    else:
        bounds = [(0.0, None)] * nv
        for g in range(G):
            for t in range(T):
                bounds[u[g, t]] = (0.0, 1.0)                 # the ub=1 that was asked for
    integrality = None
    if honour_bounds:
        # integrality is the second thing the call site asked for and the helper
        # dropped; without it u may be fractional even when [0,1]-bounded.
        integrality = np.zeros(nv)
        for g in range(G):
            for t in range(T):
                integrality[u[g, t]] = 1
    res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                  A_eq=np.array(A_eq), b_eq=np.array(b_eq), bounds=bounds,
                  integrality=integrality, method='highs')
    assert res.success, res.message
    return res.fun, res.x[u], res.x[p]


for honour in (False, True):
    obj, uu, pp = build(honour)
    tag = "bounds honoured (what the call site asked for)" if honour else "bounds dropped (what the helper actually does)"
    print(f"--- {tag}")
    print(f"    objective = {obj:,.2f}")
    print(f"    commitment u =\n{np.round(uu, 4)}")
    frac = np.sum((np.round(uu, 6) % 1) != 0)
    print(f"    fractional commitment entries: {frac}/{uu.size}"
          f"  -> verifier 'must be binary within tolerance' {'FAILS' if frac else 'passes'}")
    print()
