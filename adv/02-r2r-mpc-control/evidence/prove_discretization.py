#!/usr/bin/env python3
"""Does the doc's *other* discretization break the verifier's linearization check?

verifier/test_outputs.py computes the ground truth with Euler:
    A_d = I + dt * A_c
    B_d = dt * B_c
and asserts max|A_submitted - A_true| < 0.01, max|B_submitted - B_true| < 0.001.

state-space-linearization/SKILL.md offers TWO methods side by side without saying
which one the task expects:
    Euler:            A_d = I + dt*A_c                 B_d = dt*B_c        (line 23-24)
    Matrix exponential: A_d = expm(A_c*dt)   B_d = inv(A_c)@(A_d-I)@B_c   (line 29-30)

They agree to first order, so at the shipped dt=0.01 both pass. This script
measures how the gap grows with dt -- dt is a legitimate, authorable task input
(`system_config.json`), and the verifier recomputes its ground truth from it.
"""
import json
import numpy as np
from scipy.linalg import expm

CONFIG = json.load(open('tasks/r2r-mpc-control/environment/system_config.json'))


def continuous_jacobian(x, cfg):
    """Verbatim from verifier/test_outputs.py:compute_true_jacobian."""
    EA, Jj, Rr, fb, L = cfg["EA"], cfg["J"], cfg["R"], cfg["fb"], cfg["L"]
    n = 6
    df_dx = np.zeros((12, 12)); df_du = np.zeros((12, 6))
    for i in range(n):
        v = x[i + n]; T = x[i]
        df_dx[i, i] = -v / L
        df_dx[i, i + n] = EA / L - T / L
        if i > 0:
            vm = x[i + n - 1]; Tm = x[i - 1]
            df_dx[i, i - 1] = vm / L
            df_dx[i, i + n - 1] = -EA / L + Tm / L
        df_dx[i + n, i] = -Rr ** 2 / Jj
        df_dx[i + n, i + n] = -fb / Jj
        if i < n - 1:
            df_dx[i + n, i + 1] = Rr ** 2 / Jj
        df_du[i + n, i] = Rr / Jj
    return df_dx, df_du


def reference_state(cfg):
    T_ref = np.array(cfg["T_ref_initial"])
    v0, EA = cfg["v0"], cfg["EA"]
    v_ref = np.zeros(6); v_p, T_p = v0, 0.0
    for i in range(6):
        v_ref[i] = (EA - T_p) / (EA - T_ref[i]) * v_p
        v_p, T_p = v_ref[i], T_ref[i]
    return np.concatenate([T_ref, v_ref])


x_ref = reference_state(CONFIG)
A_c, B_c = continuous_jacobian(x_ref, CONFIG)

print(f"{'dt':>7}{'max|A_expm-A_euler|':>22}{'tol A':>8}{'max|B_expm-B_euler|':>22}{'tol B':>8}   verdict for expm")
print("-" * 88)
for dt in (0.01, 0.02, 0.05, 0.10, 0.20, 0.30):
    A_euler = np.eye(12) + dt * A_c
    B_euler = dt * B_c
    A_expm = expm(A_c * dt)
    B_expm = np.linalg.inv(A_c) @ (A_expm - np.eye(12)) @ B_c
    aerr = np.max(np.abs(A_expm - A_euler))
    berr = np.max(np.abs(B_expm - B_euler))
    ok = (aerr < 0.01) and (berr < 0.001)
    print(f"{dt:7.2f}{aerr:22.6f}{0.01:8.3f}{berr:22.6f}{0.001:8.3f}   "
          f"{'PASS (dormant)' if ok else 'FAIL (triggered)'}")
