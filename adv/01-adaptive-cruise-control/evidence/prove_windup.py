#!/usr/bin/env python3
"""Deterministic pre-check for the adaptive-cruise-control anti-windup finding.

pid-controller/SKILL.md hands the agent a copy-paste PIDController whose
`compute()` does an unconditional `self.integral += error * dt`, followed by an
"Anti-Windup" section that lists three mitigation schemes as if they were
implemented. They are not.

The task makes saturation unavoidable: the ego must reach 27 m/s from ~0 with
|a| <= 3.0 m/s^2 and a rise time under 10 s, so the actuator saturates for ~9 s
while the speed error stays near 30. That is the textbook windup setup.

This script simulates only the speed loop (t <= 30 s is cruise mode, no lead
vehicle), which is exactly what the verifier's `test_speed_control` scores:
rise time (3 -> 27 m/s) < 10 s, overshoot < 5%, steady-state error < 0.5 m/s.
"""
from __future__ import annotations

import math

SET_SPEED = 30.0
DT = 0.1
T_END = 30.0
ACC_MIN, ACC_MAX = -8.0, 3.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class PIDNoAntiWindup:
    """Verbatim behaviour of the SKILL.md compute() block."""

    def __init__(self, kp, ki, kd):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, error, dt):
        p_term = self.kp * error
        self.integral += error * dt          # <-- unconditional
        i_term = self.ki * self.integral
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        d_term = self.kd * derivative
        self.prev_error = error
        out = p_term + i_term + d_term
        return clamp(out, ACC_MIN, ACC_MAX)


class PIDAntiWindup(PIDNoAntiWindup):
    """Same controller plus conditional integration + integral clamping."""

    def __init__(self, kp, ki, kd, i_limit=5.0):
        super().__init__(kp, ki, kd)
        self.i_limit = i_limit

    def compute(self, error, dt):
        p_term = self.kp * error
        i_term = self.ki * self.integral
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        d_term = self.kd * derivative
        raw = p_term + i_term + d_term
        saturated_high = raw > ACC_MAX and error > 0
        saturated_low = raw < ACC_MIN and error < 0
        if not (saturated_high or saturated_low):       # conditional integration
            self.integral += error * dt
            self.integral = clamp(self.integral, -self.i_limit, self.i_limit)
        self.prev_error = error
        return clamp(raw, ACC_MIN, ACC_MAX)


def simulate(ctrl_cls, kp, ki, kd):
    ctrl = ctrl_cls(kp, ki, kd)
    v = 0.0
    hist = []
    t = 0.0
    while t <= T_END + 1e-9:
        a = ctrl.compute(SET_SPEED - v, DT)
        v = max(0.0, v + a * DT)
        hist.append((t, v))
        t += DT
    return hist


def metrics(hist):
    t3 = next((t for t, v in hist if v >= 3.0), None)
    t27 = next((t for t, v in hist if v >= 27.0), None)
    vmax = max(v for _, v in hist)
    v_final = hist[-1][1]
    rise = (t27 - t3) if (t3 is not None and t27 is not None) else float('inf')
    overshoot = (vmax - SET_SPEED) / SET_SPEED * 100.0
    sse = abs(SET_SPEED - v_final)
    return dict(rise=rise, overshoot=overshoot, vmax=vmax, sse=sse,
                rise_ok=rise < 10.0, overshoot_ok=overshoot < 5.0, sse_ok=sse < 0.5)


def main():
    print(f"targets: rise<10s, overshoot<5%, steady-state error<0.5 m/s "
          f"(set speed {SET_SPEED}, |a|<={ACC_MAX})\n")
    hdr = (f"{'gains (kp,ki,kd)':22}{'variant':14}{'rise s':>8}{'vmax':>8}"
           f"{'overshoot %':>13}{'SS err':>8}  verdict")
    print(hdr)
    print('-' * len(hdr))
    for kp, ki, kd in [(2.0, 0.1, 0.5), (1.0, 0.05, 0.2), (4.0, 0.3, 1.0), (0.5, 0.02, 0.1)]:
        for cls, name in ((PIDNoAntiWindup, "no anti-windup"), (PIDAntiWindup, "anti-windup")):
            m = metrics(simulate(cls, kp, ki, kd))
            ok = m['rise_ok'] and m['overshoot_ok'] and m['sse_ok']
            print(f"{str((kp,ki,kd)):22}{name:14}{m['rise']:8.2f}{m['vmax']:8.2f}"
                  f"{m['overshoot']:13.1f}{m['sse']:8.3f}  "
                  f"{'PASS' if ok else 'FAIL'}"
                  f"{'' if m['overshoot_ok'] else '  <- overshoot'}"
                  f"{'' if m['rise_ok'] else '  <- rise'}"
                  f"{'' if m['sse_ok'] else '  <- SS err'}")


if __name__ == '__main__':
    main()
