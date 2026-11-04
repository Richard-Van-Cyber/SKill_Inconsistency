#!/usr/bin/env python3
"""Solve the small DC-OPF-with-reserves instance exactly, two ways.

The verifier's fixture reads gencost[i, 4:7] as (c2, c1, c0) and never looks at
gencost[i, 0] (MODEL). Every cost row in this instance has c2 == 0, so the
verifier's model is an LP and scipy can reproduce its optimum exactly.

  verifier_cost(net)      reproduces the verifier's objective
  true_cost(net)          honours MATPOWER Type-1 rows as breakpoints

Usage: python3 solve_small.py network_small.json [network_small_type1.json]
"""
from __future__ import annotations

import json
import sys

import numpy as np
from scipy.optimize import linprog


def build_B(buses, branches):
    bus_idx = {int(b[0]): i for i, b in enumerate(buses)}
    n = len(buses)
    B = np.zeros((n, n))
    bs = []
    for br in branches:
        f, t = bus_idx[int(br[0])], bus_idx[int(br[1])]
        x = br[3]
        if x != 0:
            b = 1.0 / x
            B[f, f] += b
            B[t, t] += b
            B[f, t] -= b
            B[t, f] -= b
            bs.append(b)
        else:
            bs.append(0.0)
    return B, bs, bus_idx


def solve(net, honour_type1: bool):
    buses = np.array(net['bus'], dtype=float)
    gens = np.array(net['gen'], dtype=float)
    branches = np.array(net['branch'], dtype=float)
    gencost = np.array(net['gencost'], dtype=float)
    baseMVA = float(net['baseMVA'])
    rcap = np.array(net['reserve_capacity'], dtype=float)
    rreq = float(net['reserve_requirement'])

    nbus, ngen = len(buses), len(gens)
    B, bs, bus_idx = build_B(buses, branches)
    slack = next(i for i, b in enumerate(buses) if b[1] == 3)

    # objective coefficients: cost = sum(c1_i * baseMVA * Pg_i + c0_i)
    # (c2 is 0 for every row here; assert it rather than silently dropping it)
    for r in gencost:
        assert abs(r[4]) < 1e-12, f'row has c2={r[4]}; LP reproduction invalid'

    c = np.zeros(ngen + ngen + nbus)
    c[:ngen] = gencost[:, 5] * baseMVA          # c1 * baseMVA
    const = float(gencost[:, 6].sum())          # c0

    A_eq, b_eq = [], []
    # nodal power balance
    for i in range(nbus):
        row = np.zeros(ngen + ngen + nbus)
        for j, g in enumerate(gens):
            if bus_idx[int(g[0])] == i:
                row[j] = 1.0
        row[2 * ngen:] = -B[i, :]
        A_eq.append(row)
        b_eq.append(buses[i, 2] / baseMVA)
    # slack angle = 0
    row = np.zeros(ngen + ngen + nbus)
    row[2 * ngen + slack] = 1.0
    A_eq.append(row)
    b_eq.append(0.0)

    A_ub, b_ub = [], []
    for i in range(ngen):
        pmin, pmax = gens[i, 9] / baseMVA, gens[i, 8] / baseMVA
        r = np.zeros(ngen + ngen + nbus); r[i] = -1.0
        A_ub.append(r); b_ub.append(-pmin)
        r = np.zeros(ngen + ngen + nbus); r[i] = 1.0
        A_ub.append(r); b_ub.append(pmax)
        r = np.zeros(ngen + ngen + nbus); r[ngen + i] = 1.0
        A_ub.append(r); b_ub.append(rcap[i])
        r = np.zeros(ngen + ngen + nbus); r[i] = baseMVA; r[ngen + i] = 1.0
        A_ub.append(r); b_ub.append(gens[i, 8])
    r = np.zeros(ngen + ngen + nbus); r[ngen:2 * ngen] = -1.0
    A_ub.append(r); b_ub.append(-rreq)
    for k, br in enumerate(branches):
        rate = br[5]
        if rate <= 0:
            continue
        f, t = bus_idx[int(br[0])], bus_idx[int(br[1])]
        r = np.zeros(ngen + ngen + nbus)
        r[2 * ngen + f] = bs[k] * baseMVA
        r[2 * ngen + t] = -bs[k] * baseMVA
        A_ub.append(r.copy()); b_ub.append(rate)
        A_ub.append(-r); b_ub.append(rate)

    res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                  A_eq=np.array(A_eq), b_eq=np.array(b_eq),
                  bounds=[(None, None)] * (ngen + ngen + nbus), method='highs')
    if not res.success:
        raise SystemExit(f'LP failed: {res.message}')
    return res.fun + const, res.x[:ngen] * baseMVA, res.x[ngen:2 * ngen]


def type1_to_linear(net):
    """Replace each MODEL==1 row by the linear function its breakpoints define."""
    out = json.loads(json.dumps(net))
    for i, r in enumerate(out['gencost']):
        if int(r[0]) == 1:
            ncost = int(r[3])
            xs = [float(r[4 + 2 * j]) for j in range(ncost)]
            ys = [float(r[5 + 2 * j]) for j in range(ncost)]
            c1 = (ys[-1] - ys[0]) / (xs[-1] - xs[0])
            c0 = ys[0] - c1 * xs[0]
            row = [2.0, 0.0, 0.0, 3.0, 0.0, c1, c0]
            out['gencost'][i] = row + [0.0] * (len(r) - len(row))
    return out


def main():
    base = json.load(open(sys.argv[1]))
    print(f"=== {sys.argv[1]}")
    cost, pg, rg = solve(base, honour_type1=False)
    print(f"  verifier-objective optimum : {cost:,.2f} $/h")
    print(f"    dispatch MW {np.round(pg,2).tolist()}  reserve MW {np.round(rg,2).tolist()}")

    if len(sys.argv) > 2:
        adv = json.load(open(sys.argv[2]))
        print(f"=== {sys.argv[2]}")
        vcost, vpg, vrg = solve(adv, honour_type1=False)
        print(f"  verifier-objective optimum : {vcost:,.2f} $/h   (MODEL ignored)")
        print(f"    dispatch MW {np.round(vpg,2).tolist()}  reserve MW {np.round(vrg,2).tolist()}")
        tcost, tpg, trg = solve(type1_to_linear(adv), honour_type1=True)
        print(f"  economically correct optim.: {tcost:,.2f} $/h   (Type-1 honoured)")
        print(f"    dispatch MW {np.round(tpg,2).tolist()}  reserve MW {np.round(trg,2).tolist()}")
        gap = (tcost - vcost) / vcost
        print()
        print(f"  optimality gap a Type-1-aware agent would be scored with: {gap:+.4%}")
        print(f"  verifier tolerance: +/-0.01%  ->  {'FAILS' if abs(gap) > 1e-4 else 'passes'}")
        print(f"  ratio true/verifier optimal = {tcost/vcost:.2f}x")


if __name__ == '__main__':
    main()
