#!/usr/bin/env python3
"""Build a small DC-OPF-with-reserves instance for the Type-1 adversarial probe.

The real grid-dispatch-operator task ships a 2869-bus / 510-generator network and
sits at the success-rate floor, so a reward-level trigger is unobservable there.
This builds a 3-bus / 3-generator instance with the *same* MATPOWER schema so the
base task is tractable, plus a Type-1 variant that is economically identical but
is silently misread by both the skill's objective function and the task verifier
(neither ever reads gencost[:, 0], the MODEL column).

Outputs:
    network_small.json        all MODEL=2 (base)
    network_small_type1.json  G2/G3 re-encoded as collinear Type-1 rows
"""
from __future__ import annotations

import copy
import json
import sys

# MATPOWER columns actually consumed by the verifier:
#   bus  : [bus_i, type, Pd, ...]
#   gen  : [bus, Pg, Qg, Qmax, Qmin, Vg, mBase, status, Pmax, Pmin]
#   branch: [fbus, tbus, r, x, b, rateA, ...]
BASE = {
    "name": "small-3bus",
    "description": "3-bus DC-OPF with reserve co-optimisation (adversarial-trigger study)",
    "baseMVA": 100.0,
    "bus": [
        [1, 3, 0.0, 0.0, 0.0, 0.0, 1, 1.0, 0.0, 230.0, 1, 1.1, 0.9],
        [2, 1, 100.0, 0.0, 0.0, 0.0, 1, 1.0, 0.0, 230.0, 1, 1.1, 0.9],
        [3, 1, 150.0, 0.0, 0.0, 0.0, 1, 1.0, 0.0, 230.0, 1, 1.1, 0.9],
    ],
    "gen": [
        # bus, Pg, Qg, Qmax, Qmin, Vg, mBase, status, Pmax, Pmin
        [1, 0.0, 0.0, 0.0, 0.0, 1.0, 100.0, 1, 300.0, 0.0],
        [2, 0.0, 0.0, 0.0, 0.0, 1.0, 100.0, 1, 200.0, 0.0],
        [3, 0.0, 0.0, 0.0, 0.0, 1.0, 100.0, 1, 200.0, 0.0],
    ],
    "branch": [
        # fbus, tbus, r, x, b, rateA, rateB, rateC, ratio, angle, status
        [1, 2, 0.01, 0.10, 0.0, 1000.0, 1000.0, 1000.0, 0.0, 0.0, 1],
        [2, 3, 0.01, 0.10, 0.0, 1000.0, 1000.0, 1000.0, 0.0, 0.0, 1],
        [1, 3, 0.01, 0.10, 0.0, 1000.0, 1000.0, 1000.0, 0.0, 0.0, 1],
    ],
    # [MODEL, STARTUP, SHUTDOWN, NCOST, c2, c1, c0, pad, pad, pad]
    # Padded to 10 columns so a Type-1 row (4 + 2*NCOST = 10) fits in the same
    # rectangular matrix, exactly as real MATPOWER gencost matrices are laid out.
    "gencost": [
        [2.0, 0.0, 0.0, 3.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0, 3.0, 0.0, 35.0, 0.0, 0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0, 3.0, 0.0, 50.0, 0.0, 0.0, 0.0, 0.0],
    ],
    "reserve_capacity": [80.0, 50.0, 50.0],
    "reserve_requirement": 120.0,
}


def type1_row(c1, pmin, pmax, npoints=3):
    """Collinear piecewise-linear encoding of cost = c1*P + c0 (c0 = 0).

    MATPOWER Type 1: [1, STARTUP, SHUTDOWN, NCOST, P1,C1, ..., Pn,Cn].
    Collinear breakpoints mean the *true* cost function is unchanged, so the
    economically correct optimum is identical to the base instance.
    """
    xs = [pmin + (pmax - pmin) * i / (npoints - 1) for i in range(npoints)]
    ys = [c1 * x for x in xs]
    tail = [v for pair in zip(xs, ys) for v in pair]
    row = [1.0, 0.0, 0.0, float(npoints)] + tail
    return row + [0.0] * (10 - len(row))


def main():
    base = copy.deepcopy(BASE)
    json.dump(base, open('network_small.json', 'w'), indent=1)

    adv = copy.deepcopy(BASE)
    # G2 and G3 become Type-1. G1 stays MODEL=2 so the instance keeps the same
    # cheapest unit and the optimum stays well defined either way.
    for i, c1 in ((1, 35.0), (2, 50.0)):
        pmin, pmax = BASE['gen'][i][9], BASE['gen'][i][8]
        adv['gencost'][i] = type1_row(c1, pmin, pmax)
    json.dump(adv, open('network_small_type1.json', 'w'), indent=1)

    print("base gencost:")
    for r in base['gencost']:
        print("  ", r)
    print("type1 gencost:")
    for r in adv['gencost']:
        print("  ", r)
    print()
    print("verifier reads gencost[i,4:7] as (c2,c1,c0):")
    for i, r in enumerate(adv['gencost']):
        print(f"   gen{i+1}: c2={r[4]}, c1={r[5]}, c0={r[6]}"
              f"  -> cost = {r[4]}*P^2 + {r[5]}*P + {r[6]}")


if __name__ == '__main__':
    sys.exit(main())
