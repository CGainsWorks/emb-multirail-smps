"""Averaged state space models of the power stages.

Nothing here is a remembered textbook formula. Each converter is written down
as two linear systems, one per switch state, from Kirchhoff's laws with the
parasitics included. State space averaging and linearisation then produce the
control-to-output, line-to-output and control-to-inductor-current transfer
functions numerically.

That matters for two reasons. The closed forms everyone quotes (the boost right
half plane zero at ``D'^2 R / L``, the buck LC double pole at ``1/2pi sqrt(LC)``)
drop the parasitics, so they are only ever approximations; and quoting a
formula from memory is exactly the step where a sign or a ``D'`` goes missing.
``docs/design_notes.md`` writes the closed forms out by hand, and
``tests/test_smallsignal.py`` checks the numeric model agrees with them to
within the error the dropped parasitics explain.

Conventions
-----------
State vector  ``x = [iL, vC]``
Input vector  ``u = [vin, iout]``
Output        ``vout``

``r_load`` is the resistive load present at the operating point. The ``iout``
input is a *perturbation* current source used for output impedance and load
steps; it is zero at the operating point.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SwitchedModel:
    """A converter as two LTI systems plus the averaged, linearised result."""

    a_on: np.ndarray
    b_on: np.ndarray
    c_on: np.ndarray
    d_on: np.ndarray
    a_off: np.ndarray
    b_off: np.ndarray
    c_off: np.ndarray
    d_off: np.ndarray
    #: Row selecting the inductor current as an output.
    c_il: np.ndarray

    def averaged(self, duty: float):
        a = duty * self.a_on + (1 - duty) * self.a_off
        b = duty * self.b_on + (1 - duty) * self.b_off
        c = duty * self.c_on + (1 - duty) * self.c_off
        d = duty * self.d_on + (1 - duty) * self.d_off
        return a, b, c, d

    def operating_point(self, duty: float, u: np.ndarray) -> np.ndarray:
        """Steady state ``x`` for a given duty ratio and input vector."""
        a, b, _, _ = self.averaged(duty)
        return np.linalg.solve(-a, b @ u)

    def v_out_dc(self, duty: float, u: np.ndarray) -> float:
        a, b, c, d = self.averaged(duty)
        x = np.linalg.solve(-a, b @ u)
        return float(c @ x + d @ u)

    def duty_for_vout(self, v_target: float, u: np.ndarray,
                      lo: float = 1e-4, hi: float = 0.95) -> float:
        """Bisect for the duty ratio that gives ``v_target`` in steady state."""
        f_lo = self.v_out_dc(lo, u) - v_target
        f_hi = self.v_out_dc(hi, u) - v_target
        if f_lo * f_hi > 0:
            raise ValueError("target output voltage not reachable in this range")
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            f_mid = self.v_out_dc(mid, u) - v_target
            if f_lo * f_mid <= 0:
                hi, f_hi = mid, f_mid
            else:
                lo, f_lo = mid, f_mid
        return 0.5 * (lo + hi)

    def duty_input_vectors(self, duty: float, u: np.ndarray):
        """The ``Bd`` and ``Dd`` terms produced by linearising about ``duty``."""
        x = self.operating_point(duty, u)
        bd = (self.a_on - self.a_off) @ x + (self.b_on - self.b_off) @ u
        dd = float((self.c_on - self.c_off) @ x + (self.d_on - self.d_off) @ u)
        return x, bd, dd

    # ------------------------------------------------------------------
    # Frequency responses
    # ------------------------------------------------------------------

    @staticmethod
    def _resp(f_hz, a, b_vec, c_row, d_scalar) -> np.ndarray:
        f_hz = np.atleast_1d(np.asarray(f_hz, dtype=float))
        s = 2j * np.pi * f_hz
        eye = np.eye(a.shape[0])
        out = np.empty(f_hz.shape, dtype=complex)
        for k, sk in enumerate(s):
            xk = np.linalg.solve(sk * eye - a, b_vec)
            out[k] = c_row @ xk + d_scalar
        return out

    def g_vd(self, f_hz, duty: float, u: np.ndarray) -> np.ndarray:
        """Control (duty) to output voltage."""
        a, _, c, _ = self.averaged(duty)
        _, bd, dd = self.duty_input_vectors(duty, u)
        return self._resp(f_hz, a, bd, c, dd)

    def g_id(self, f_hz, duty: float, u: np.ndarray) -> np.ndarray:
        """Control (duty) to inductor current."""
        a, _, _, _ = self.averaged(duty)
        _, bd, _ = self.duty_input_vectors(duty, u)
        return self._resp(f_hz, a, bd, self.c_il, 0.0)

    def g_vg(self, f_hz, duty: float, u: np.ndarray) -> np.ndarray:
        """Input voltage to output voltage, the open loop audio susceptibility."""
        a, b, c, d = self.averaged(duty)
        return self._resp(f_hz, a, b[:, 0], c, float(d[0]))

    def z_out(self, f_hz, duty: float, u: np.ndarray) -> np.ndarray:
        """Open loop output impedance seen from the load current input."""
        a, b, c, d = self.averaged(duty)
        return -self._resp(f_hz, a, b[:, 1], c, float(d[1]))


def _stage(l_h: float, c_f: float, r_dcr: float, r_esr: float, r_load: float,
           r_series: float, vin_gain: float, inductor_feeds_output: bool):
    """One switch state, built from Kirchhoff's laws.

    ``inductor_feeds_output`` is True when the inductor current flows into the
    output node in this state. That is the on state for a buck and the off
    state for a boost, which is the whole structural difference between them.
    """
    gl = 1.0 / r_load
    k = 1.0 / (1.0 + r_esr * gl)          # ESR / load divider factor

    # vout = k*(vC + Resr*(iL_to_out - iout))
    il_gain = 1.0 if inductor_feeds_output else 0.0
    c_row = np.array([k * r_esr * il_gain, k])
    d_row = np.array([0.0, -k * r_esr])

    a = np.zeros((2, 2))
    b = np.zeros((2, 2))

    # Capacitor node: iC = iL_to_out - iout - gl*vout
    a[1, 0] = (il_gain * (1.0 - gl * k * r_esr)) / c_f
    a[1, 1] = (-gl * k) / c_f
    b[1, 0] = 0.0
    b[1, 1] = (-1.0 + gl * k * r_esr) / c_f

    # Inductor: L diL/dt = vin_gain*vin - iL*(Rseries + Rdcr) - vout*(if connected)
    a[0, 0] = -(r_series + r_dcr) / l_h
    b[0, 0] = vin_gain / l_h
    if inductor_feeds_output:
        a[0, 0] += -c_row[0] / l_h
        a[0, 1] += -c_row[1] / l_h
        b[0, 1] += -d_row[1] / l_h

    return a, b, c_row, d_row


def buck_model(l_h: float, c_f: float, r_dcr: float, r_esr: float,
               rds_hs: float, rds_ls: float, r_load: float) -> SwitchedModel:
    """Synchronous buck.

    On state, high side conducting::

        L diL/dt = vin - iL(Rhs + Rdcr) - vout
        C dvC/dt = iL - iout - vout/Rload
        vout     = vC + Resr(iL - iout - vout/Rload)

    Off state is the same with ``vin -> 0`` and ``Rhs -> Rls``. The inductor
    feeds the output node in both states, which is why a buck has no right half
    plane zero.
    """
    on = _stage(l_h, c_f, r_dcr, r_esr, r_load, rds_hs, 1.0, True)
    off = _stage(l_h, c_f, r_dcr, r_esr, r_load, rds_ls, 0.0, True)
    return SwitchedModel(*on, *off, c_il=np.array([1.0, 0.0]))


def boost_model(l_h: float, c_f: float, r_dcr: float, r_esr: float,
                rds_lo: float, rds_hi: float, r_load: float) -> SwitchedModel:
    """Synchronous boost.

    On state, low side conducting, inductor charging and disconnected from the
    output::

        L diL/dt = vin - iL(Rlo + Rdcr)
        C dvC/dt = -iout - vout/Rload

    Off state, high side conducting::

        L diL/dt = vin - iL(Rhi + Rdcr) - vout
        C dvC/dt = iL - iout - vout/Rload

    Increasing the duty ratio takes the inductor away from the output for
    longer, so the output voltage initially falls before the larger inductor
    current arrives. That is the right half plane zero, and it falls straight
    out of the two matrices above without needing to be written in by hand.
    """
    on = _stage(l_h, c_f, r_dcr, r_esr, r_load, rds_lo, 1.0, False)
    off = _stage(l_h, c_f, r_dcr, r_esr, r_load, rds_hi, 1.0, True)
    return SwitchedModel(*on, *off, c_il=np.array([1.0, 0.0]))


# --------------------------------------------------------------------------
# Peak current mode inner loop, Ridley sampled data model
# --------------------------------------------------------------------------

def he(f_hz, f_sw: float) -> np.ndarray:
    """Sampling gain of the peak current comparator.

    ``He(s) = 1 + s/(wn Qz) + (s/wn)^2`` with ``wn = pi/Ts`` and ``Qz = -2/pi``.
    It is the second order approximation to ``sTs/(e^{sTs} - 1)``, and it is
    what puts a pair of poles at half the switching frequency into a current
    mode control-to-output response. Drop it and the model will happily predict
    a crossover above fsw/2 that the real converter cannot deliver.
    """
    f_hz = np.atleast_1d(np.asarray(f_hz, dtype=float))
    ts = 1.0 / f_sw
    wn = np.pi / ts
    qz = -2.0 / np.pi
    s = 2j * np.pi * f_hz
    return 1.0 + s / (wn * qz) + (s / wn) ** 2


@dataclass(frozen=True)
class CurrentModeLoop:
    """Closes the peak current comparator loop around a switched model.

    ``Gvc = Gvd * Fm / (1 + Fm Ri He Gid)``

    This is the inner loop written out rather than the closed form for the
    resulting poles. Every parasitic in the state space model survives into the
    result, and the dominant pole, the ESR zero, the right half plane zero and
    the fsw/2 pole pair all appear without being placed there by hand.
    """

    model: SwitchedModel
    duty: float
    u: np.ndarray
    f_sw: float
    #: Current sense gain in volts per amp, shunt resistance times amplifier gain.
    ri: float
    #: Artificial ramp slope in volts per second, referred to the sense node.
    se: float
    #: Rising sensed current slope in volts per second.
    sn: float

    @property
    def fm(self) -> float:
        """Modulator gain, ``1/((Sn + Se) Ts)``."""
        return 1.0 / ((self.sn + self.se) / self.f_sw)

    @property
    def mc(self) -> float:
        """Slope compensation factor ``mc = 1 + Se/Sn``."""
        return 1.0 + self.se / self.sn

    @property
    def q_sampling(self) -> float:
        """``Qp = 1/(pi (mc D' - 0.5))``, damping of the fsw/2 pole pair."""
        dp = 1.0 - self.duty
        return 1.0 / (np.pi * (self.mc * dp - 0.5))

    def g_vc(self, f_hz) -> np.ndarray:
        """Control voltage to output voltage with the current loop closed."""
        g_vd = self.model.g_vd(f_hz, self.duty, self.u)
        g_id = self.model.g_id(f_hz, self.duty, self.u)
        h = he(f_hz, self.f_sw)
        return g_vd * self.fm / (1.0 + self.fm * self.ri * h * g_id)

    def t_inner(self, f_hz) -> np.ndarray:
        """Inner current loop gain, used to check subharmonic margin."""
        g_id = self.model.g_id(f_hz, self.duty, self.u)
        return self.fm * self.ri * he(f_hz, self.f_sw) * g_id
