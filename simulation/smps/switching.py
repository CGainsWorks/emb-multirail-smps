"""Cycle accurate closed loop simulation of the switching converters.

This is the part that earns the word "validation". The averaged models in
:mod:`smps.statespace` are an approximation with known blind spots: they assume
the ripple is small, they smear the modulator into a gain, and for current mode
they bolt the sampling effect on afterwards as ``He(s)``. The only way to know
whether the compensator designed against that approximation gives the margins
claimed is to run the switching converter itself and measure.

So that is what happens here. Each switch state is an exact linear system. The
solver propagates the state with a matrix exponential evaluated through an
eigendecomposition, so there is no fixed step integration error and no
numerical damping, and the switching instant is found by root finding on the
real comparator condition rather than being quantised onto a time grid.

The compensator is carried as extra states in the same augmented system, so the
loop really is closed cycle by cycle. So is the small signal injection used for
the loop measurement: it is a two state oscillator rather than a value held
constant across each cycle, because a held value is a zero order hold and would
add ``exp(-s Tsw/2)`` of phase lag to the answer that the real converter does
not have.

Augmented system, per switch state::

    x = [plant states ; compensator states ; injection oscillator]
    u = [vin , iout_perturbation , v_target]
    A = [[Ap,      0,   0     ],
         [-Bc Cp,  Ac, -Bc a e1'],
         [0,       0,   Aosc  ]]
    B = [[Bp,     0 ],
         [-Bc Dp, Bc],
         [0,      0 ]]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np
from scipy.signal import tf2ss

from .statespace import SwitchedModel


# --------------------------------------------------------------------------
# Exact propagation of a linear system over an arbitrary interval
# --------------------------------------------------------------------------

class Propagator:
    """``x(t+dt) = Phi(dt) x + Gamma(dt) u`` for one switch state.

    Built from an eigendecomposition once, then every step is two small matrix
    products. Exact for any ``dt``, which is what lets the switching instant be
    placed wherever the comparator says rather than on a grid.
    """

    def __init__(self, a: np.ndarray, b: np.ndarray):
        self.a = a
        self.b = b
        lam, v = np.linalg.eig(a.astype(complex))
        if np.linalg.cond(v) > 1e13:  # pragma: no cover - defensive
            raise np.linalg.LinAlgError("state matrix is too close to defective")
        self.lam = lam
        self.v = v
        self.v_inv = np.linalg.inv(v)

    def step(self, x: np.ndarray, u: np.ndarray, dt: float) -> np.ndarray:
        e = np.exp(self.lam * dt)
        # (e^{lam dt} - 1)/lam, with the removable singularity at lam = 0
        # handled explicitly because the compensator integrator and the
        # injection oscillator both sit on or near the imaginary axis.
        small = np.abs(self.lam * dt) < 1e-9
        g = np.where(small, dt, (e - 1.0) / np.where(small, 1.0, self.lam))
        z = self.v_inv @ x.astype(complex)
        w = self.v_inv @ (self.b @ u).astype(complex)
        return np.real(self.v @ (e * z + g * w))


# --------------------------------------------------------------------------
# Compensators as transfer functions, ready to be embedded
# --------------------------------------------------------------------------

def type_ii_tf(rc: float, cc: float, cp: float, gm: float, ro: float,
               k_div: float):
    """``Gc(s) = k_div * gm * Z(s)`` as numerator and denominator coefficients.

    ``Z = ro || (Rc + 1/sCc) || 1/sCp``, so

        Z(s) = (1 + s Rc Cc) / (s^2 Rc Cc Cp + s(Rc Cc/ro + Cc + Cp) + 1/ro)
    """
    num = np.array([rc * cc, 1.0]) * k_div * gm
    den = np.array([rc * cc * cp, rc * cc / ro + cc + cp, 1.0 / ro])
    return num, den


def type_iii_tf(r1: float, r3: float, rf: float, cf1: float, cf2: float,
                cf3: float):
    """``Gc(s) = Zf/Zi`` as numerator and denominator coefficients.

        Zf = (1 + s Rf Cf1) / (s(Cf1+Cf2) + s^2 Rf Cf1 Cf2)
        Zi = R1 (1 + s R3 Cf3) / (1 + s (R1+R3) Cf3)
    """
    num = np.convolve([rf * cf1, 1.0], [(r1 + r3) * cf3, 1.0])
    den = r1 * np.convolve([rf * cf1 * cf2, cf1 + cf2, 0.0], [r3 * cf3, 1.0])
    return num, den


def integrator_tf(f_unity_hz: float):
    """``Gc(s) = 2 pi f_unity / s``, used to probe the plant on its own."""
    return np.array([2 * np.pi * f_unity_hz]), np.array([1.0, 0.0])


# --------------------------------------------------------------------------
# The simulator
# --------------------------------------------------------------------------

@dataclass
class SimConfig:
    model: SwitchedModel
    comp_num: np.ndarray
    comp_den: np.ndarray
    f_sw: float
    v_in: float
    v_target: float
    mode: Literal["peak-current", "voltage"]
    #: Peak current mode only.
    ri: float = 0.0
    se_v_per_s: float = 0.0
    #: Voltage mode only, trailing edge ramp rising from v_ramp_low by v_ramp_pp.
    v_ramp_low: float = 0.0
    v_ramp_pp: float = 1.0
    d_min: float = 0.01
    d_max: float = 0.95
    #: Steady state guesses used to start the solver close to the answer.
    il_init: float = 0.0
    vc_init: float = 0.0
    vcomp_init: float = 0.0


@dataclass
class SimResult:
    t: np.ndarray
    v_out: np.ndarray
    i_l: np.ndarray
    duty: np.ndarray
    v_comp: np.ndarray
    #: One sample per switching cycle, taken at the start of the cycle.
    t_cycle: np.ndarray
    v_out_cycle: np.ndarray
    v_a_cycle: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v_b_cycle: np.ndarray = field(default_factory=lambda: np.zeros(0))


class ConverterSim:
    """One converter, closed loop, simulated switching cycle by switching cycle."""

    def __init__(self, cfg: SimConfig, inj_f_hz: float = 0.0, inj_amp_v: float = 0.0):
        self.cfg = cfg
        self.inj_f_hz = inj_f_hz
        self.inj_amp_v = inj_amp_v

        m = cfg.model
        ac, bc, cc, dc = tf2ss(np.atleast_1d(cfg.comp_num), np.atleast_1d(cfg.comp_den))
        self.ac, self.bc, self.cc, self.dc = ac, bc, cc, dc
        self.n_p = m.a_on.shape[0]
        self.n_c = ac.shape[0]
        self.n_o = 2 if inj_f_hz > 0 else 0
        self.n = self.n_p + self.n_c + self.n_o

        self.on = self._augment(m.a_on, m.b_on, m.c_on, m.d_on)
        self.off = self._augment(m.a_off, m.b_off, m.c_off, m.d_off)
        self.prop_on = Propagator(*self.on[:2])
        self.prop_off = Propagator(*self.off[:2])

    def _augment(self, ap, bp, cp, dp):
        n_p, n_c, n_o = self.n_p, self.n_c, self.n_o
        n = n_p + n_c + n_o
        a = np.zeros((n, n))
        b = np.zeros((n, 3))
        a[:n_p, :n_p] = ap
        a[n_p:n_p + n_c, :n_p] = -self.bc @ cp.reshape(1, -1)
        a[n_p:n_p + n_c, n_p:n_p + n_c] = self.ac
        b[:n_p, :2] = bp
        b[n_p:n_p + n_c, :2] = -self.bc @ dp.reshape(1, -1)
        b[n_p:n_p + n_c, 2:3] = self.bc
        if n_o:
            w = 2 * np.pi * self.inj_f_hz
            a[n_p + n_c:, n_p + n_c:] = np.array([[0.0, w], [-w, 0.0]])
            # e = v_target - vout - inj, and inj = amp * x_osc[0]
            a[n_p:n_p + n_c, n_p + n_c] = (-self.bc * self.inj_amp_v).ravel()
        c_v = np.concatenate([cp, np.zeros(n_c + n_o)])
        d_v = np.array([0.0, dp[1], 0.0])
        return a, b, c_v, d_v

    # ------------------------------------------------------------------

    def v_out(self, x, u, state: str) -> float:
        c_v, d_v = (self.on[2], self.on[3]) if state == "on" else (self.off[2], self.off[3])
        return float(np.asarray(c_v @ x + d_v @ u).item())

    def v_comp(self, x) -> float:
        return float((self.cc @ x[self.n_p:self.n_p + self.n_c]).item())

    def injection(self, x) -> float:
        if not self.n_o:
            return 0.0
        return self.inj_amp_v * float(x[self.n_p + self.n_c])

    def initial_state(self) -> np.ndarray:
        cfg = self.cfg
        x = np.zeros(self.n)
        x[0] = cfg.il_init
        x[1] = cfg.vc_init
        # Minimum norm compensator state giving the wanted COMP output, so the
        # integrator does not have to wind up from zero.
        c = self.cc.reshape(1, -1)
        x[self.n_p:self.n_p + self.n_c] = np.linalg.pinv(c) @ np.array([cfg.vcomp_init])
        return x

    def start_injection(self, x: np.ndarray) -> np.ndarray:
        """Set the oscillator to ``[sin, cos] = [0, 1]`` so injection starts at zero."""
        if self.n_o:
            x = x.copy()
            x[self.n_p + self.n_c] = 0.0
            x[self.n_p + self.n_c + 1] = 1.0
        return x

    # ------------------------------------------------------------------
    # One switching cycle
    # ------------------------------------------------------------------

    def _find_turn_off(self, x, u) -> float:
        cfg = self.cfg
        v_comp_0 = self.v_comp(x)

        if cfg.mode == "peak-current":
            def resid(dt):
                xn = self.prop_on.step(x, u, dt)
                return cfg.ri * xn[0] + cfg.se_v_per_s * dt - self.v_comp(xn)
            slope = float(cfg.ri * (self.on[0][0] @ x + self.on[1][0] @ u)
                          + cfg.se_v_per_s)
            guess = (v_comp_0 - cfg.ri * x[0]) / slope if slope > 0 else 1.0 / cfg.f_sw
        else:
            def resid(dt):
                xn = self.prop_on.step(x, u, dt)
                return self.v_comp(xn) - (cfg.v_ramp_low + cfg.v_ramp_pp * dt * cfg.f_sw)
            guess = (v_comp_0 - cfg.v_ramp_low) / cfg.v_ramp_pp / cfg.f_sw

        lo, hi = cfg.d_min / cfg.f_sw, cfg.d_max / cfg.f_sw
        t1 = min(max(guess, lo), hi)
        r1 = resid(t1)
        t2 = min(max(t1 * 1.001 + 1e-13, lo), hi)
        r2 = resid(t2)
        for _ in range(20):
            if not np.isfinite(r2) or abs(r2 - r1) < 1e-20:
                break
            t3 = t2 - r2 * (t2 - t1) / (r2 - r1)
            t3 = min(max(t3, lo), hi)
            t1, r1 = t2, r2
            t2, r2 = t3, resid(t3)
            if abs(t2 - t1) < 1e-15:
                break
        return min(max(t2, lo), hi)

    # ------------------------------------------------------------------

    def run(self, n_cycles: int, u_of_cycle: Callable[[int], np.ndarray],
            samples_per_interval: int = 0,
            inject_from_cycle: int | None = None,
            dense_from_cycle: int = 0) -> SimResult:
        """Run ``n_cycles`` switching cycles.

        ``u_of_cycle(k)`` returns ``[vin, iout_perturbation, v_target]`` for
        cycle ``k``, which is how line steps and load steps are applied.

        Sampling once per switching cycle is deliberate. Every quantity that is
        periodic at the switching frequency lands on the DC bin of that sample
        sequence, so the ripple is rejected exactly rather than approximately.
        See :mod:`smps.loopmeas`.
        """
        cfg = self.cfg
        ts = 1.0 / cfg.f_sw
        x = self.initial_state()

        t_cycle = np.empty(n_cycles)
        v_cycle = np.empty(n_cycles)
        va_cycle = np.empty(n_cycles)
        vb_cycle = np.empty(n_cycles)
        duty = np.empty(n_cycles)

        dense_t: list[float] = []
        dense_v: list[float] = []
        dense_i: list[float] = []
        dense_c: list[float] = []

        t0 = 0.0
        for k in range(n_cycles):
            if inject_from_cycle is not None and k == inject_from_cycle:
                x = self.start_injection(x)
            u = np.asarray(u_of_cycle(k), dtype=float)

            v_a = self.v_out(x, u, "off")
            inj = self.injection(x)
            t_cycle[k] = t0
            v_cycle[k] = v_a
            va_cycle[k] = v_a
            vb_cycle[k] = v_a + inj

            t_on = self._find_turn_off(x, u)
            t_off = ts - t_on
            duty[k] = t_on / ts

            if samples_per_interval > 0 and k >= dense_from_cycle:
                for state, dur in (("on", t_on), ("off", t_off)):
                    prop = self.prop_on if state == "on" else self.prop_off
                    sub = dur / samples_per_interval
                    for _ in range(samples_per_interval):
                        x = prop.step(x, u, sub)
                        t0 += sub
                        dense_t.append(t0)
                        dense_v.append(self.v_out(x, u, state))
                        dense_i.append(x[0])
                        dense_c.append(self.v_comp(x))
            else:
                x = self.prop_on.step(x, u, t_on)
                x = self.prop_off.step(x, u, t_off)
                t0 += ts

        return SimResult(
            t=np.array(dense_t), v_out=np.array(dense_v), i_l=np.array(dense_i),
            duty=duty, v_comp=np.array(dense_c),
            t_cycle=t_cycle, v_out_cycle=v_cycle,
            v_a_cycle=va_cycle, v_b_cycle=vb_cycle,
        )
