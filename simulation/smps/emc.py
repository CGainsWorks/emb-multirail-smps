"""Conducted emissions pre-scan, modelled.

What this is
------------
The input current of a buck converter is a pulse train, not a smooth DC draw.
Its harmonics run out to well past 30 MHz. The input filter has to shunt those
harmonics back into the loop that made them, so that what reaches the supply
lead stays under the limit line. This module builds the harmonic spectrum of
that pulse train from the trapezoidal waveform, pushes it through the input
filter and a 50 ohm / 5 uH LISN, and plots the result in dB microvolts against
a limit line.

What this is not
----------------
A measurement. There is no chamber, no LISN, no spectrum analyser and no board.
It is also differential mode only. On real hardware the common mode path,
driven by the dv/dt of the switch node into parasitic capacitance to the
chassis and to earth, is very often the term that actually fails, and it
depends on layout details that do not exist yet. So a pass here means "the
differential mode filter is sized sensibly", not "this board will pass".

Limit line
----------
The DC input of this board is not a mains port, so EN 55032 conducted mains
limits do not formally apply to it. The Class B line is used here as a
reference envelope because it is the strictest commonly quoted one and because
a pre-scan needs something to compare against. The real limit has to come from
whatever the end product is certified to.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import components as C
from .sizing import buck_duty
from .spec import rail


# --------------------------------------------------------------------------
# Input filter
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class InputFilter:
    """Two stage differential mode input filter.

    Stage 1 is the local ceramic decoupling plus an aluminium polymer bulk
    capacitor, which is what actually carries the switching current. Stage 2 is
    the differential mode inductance of the common mode choke working against a
    film capacitor, which is what stops the residue reaching the lead.
    """

    c1_f: float = C.BUCK5["Cin_F"]
    c1_esr_ohm: float = C.BUCK5["Cin_esr_ohm"]
    c1_esl_h: float = 1.2e-9
    cbulk_f: float = C.BUCK5["Cbulk_F"]
    cbulk_esr_ohm: float = C.BUCK5["Cbulk_esr_ohm"]
    cbulk_esl_h: float = 6e-9
    #: Differential (leakage) inductance of the common mode choke.
    l_dm_h: float = 10e-6
    l_dm_esr_ohm: float = 40e-3
    c2_f: float = 2.2e-6
    c2_esr_ohm: float = 8e-3
    c2_esl_h: float = 3e-9
    #: LISN, the CISPR artificial network the analyser actually sees.
    lisn_l_h: float = 5e-6
    lisn_r_ohm: float = 50.0
    #: Supply lead, used for the stability check rather than the emissions one.
    lead_l_h: float = 1e-6
    lead_r_ohm: float = 50e-3

    def _z_cap(self, f, c, esr, esl):
        s = 2j * np.pi * f
        return esr + s * esl + 1.0 / (s * c)

    def transfer_ohm(self, f_hz) -> np.ndarray:
        """Volts at the LISN resistor per amp of converter input ripple current.

        The converter is a current source at the switch node input. That
        current divides between the local capacitor bank and everything
        upstream of it; whatever goes upstream divides again at the choke.
        """
        f = np.atleast_1d(np.asarray(f_hz, dtype=float))
        s = 2j * np.pi * f

        z_local = 1.0 / (1.0 / self._z_cap(f, self.c1_f, self.c1_esr_ohm, self.c1_esl_h)
                         + 1.0 / self._z_cap(f, self.cbulk_f, self.cbulk_esr_ohm,
                                             self.cbulk_esl_h))
        z_c2 = self._z_cap(f, self.c2_f, self.c2_esr_ohm, self.c2_esl_h)
        z_lisn = self.lisn_r_ohm + s * self.lisn_l_h
        z_choke = self.l_dm_esr_ohm + s * self.l_dm_h

        # Upstream of the local bank: choke into (C2 parallel LISN).
        z_c2_lisn = 1.0 / (1.0 / z_c2 + 1.0 / z_lisn)
        z_up = z_choke + z_c2_lisn

        # Current divider between the local bank and the upstream branch.
        i_up = z_local / (z_local + z_up)
        # Of that, the fraction into the LISN rather than into C2.
        i_lisn = i_up * z_c2 / (z_c2 + z_lisn)
        return np.abs(i_lisn * self.lisn_r_ohm)


    def z_out_ohm(self, f_hz) -> np.ndarray:
        """Filter output impedance with the source shorted.

        This is the quantity that has to stay well below the converter input
        impedance. A converter running closed loop draws constant power, so
        below its loop bandwidth it looks like a *negative* resistance of
        ``-Vin^2/Pin``. Put a lightly damped LC filter in front of that and the
        pair oscillates, whatever the control loop margins say. Middlebrook's
        criterion is the reason the bulk capacitor on this board is 220 uF
        rather than the 47 uF the ripple alone would ask for: the peak of this
        impedance is roughly ``Q * sqrt(L/C)``, so the capacitance sets how
        high the peak can get before any damping is applied at all. The ESR of
        an aluminium polymer part then supplies part of that damping, with the
        input inductor's own resistance and the supply lead supplying the rest.
        """
        f = np.atleast_1d(np.asarray(f_hz, dtype=float))
        s = 2j * np.pi * f
        z_local = 1.0 / (1.0 / self._z_cap(f, self.c1_f, self.c1_esr_ohm, self.c1_esl_h)
                         + 1.0 / self._z_cap(f, self.cbulk_f, self.cbulk_esr_ohm,
                                             self.cbulk_esl_h))
        z_c2 = self._z_cap(f, self.c2_f, self.c2_esr_ohm, self.c2_esl_h)
        z_src = self.lead_r_ohm + s * self.lead_l_h
        z_up = (self.l_dm_esr_ohm + s * self.l_dm_h) + 1.0 / (1.0 / z_c2 + 1.0 / z_src)
        return np.abs(1.0 / (1.0 / z_local + 1.0 / z_up))


# --------------------------------------------------------------------------
# Source spectrum
# --------------------------------------------------------------------------

def trapezoid_harmonics(i_low: float, i_high: float, duty: float, f_sw: float,
                        t_rise: float, t_fall: float, n_max: int):
    """Fourier amplitudes of the buck input current pulse train.

    The pulse is a trapezoid: it steps up to ``i_low`` in ``t_rise``, ramps to
    ``i_high`` across the on time and falls to zero in ``t_fall``. Using the
    trapezoid rather than a rectangle matters, because the rectangle's
    harmonics only roll off at 20 dB per decade for ever, while the real edge
    puts a second corner at ``1/(pi t_rise)`` and everything above that falls
    at 40 dB per decade. Above about 10 MHz that is the difference between a
    plausible prediction and nonsense.
    """
    n = np.arange(1, n_max + 1)
    f = n * f_sw
    i_avg = 0.5 * (i_low + i_high)
    # Rectangular pulse of height i_avg and width duty*T, then two sinc
    # corners for the finite edges.
    a_rect = 2.0 * i_avg * np.abs(np.sinc(n * duty))* duty
    edge = np.abs(np.sinc(f * 0.5 * (t_rise + t_fall)))
    return f, a_rect * edge


# --------------------------------------------------------------------------
# Limit lines
# --------------------------------------------------------------------------

def en55032_class_b_qp_dbuv(f_hz) -> np.ndarray:
    """Quasi peak conducted limit, used here only as a reference envelope."""
    f = np.atleast_1d(np.asarray(f_hz, dtype=float))
    out = np.full(f.shape, np.nan)
    band1 = (f >= 150e3) & (f < 500e3)
    # 66 dBuV at 150 kHz falling linearly with log f to 56 dBuV at 500 kHz.
    out[band1] = 66.0 - 10.0 * (np.log10(f[band1] / 150e3) / np.log10(500e3 / 150e3))
    out[(f >= 500e3) & (f < 5e6)] = 56.0
    out[(f >= 5e6) & (f <= 30e6)] = 60.0
    return out


def dbuv(volts) -> np.ndarray:
    v = np.maximum(np.abs(np.asarray(volts)), 1e-18)
    return 20.0 * np.log10(v / 1e-6)


# --------------------------------------------------------------------------
# The pre-scan
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PrescanResult:
    f_hz: np.ndarray
    v_dbuv: np.ndarray
    limit_dbuv: np.ndarray

    @property
    def in_band(self) -> np.ndarray:
        return np.isfinite(self.limit_dbuv)

    @property
    def margin_db(self) -> np.ndarray:
        return self.limit_dbuv - self.v_dbuv

    @property
    def worst_margin_db(self) -> float:
        m = self.margin_db[self.in_band]
        return float(np.min(m)) if m.size else float("nan")

    @property
    def worst_frequency_hz(self) -> float:
        m = self.margin_db.copy()
        m[~self.in_band] = np.inf
        return float(self.f_hz[int(np.argmin(m))])

    def rows(self) -> list[dict]:
        return [
            {"f_hz": round(float(f), 1), "level_dbuv": round(float(v), 2),
             "limit_dbuv": (round(float(l), 2) if np.isfinite(l) else "out of band"),
             "margin_db": (round(float(l - v), 2) if np.isfinite(l) else "")}
            for f, v, l in zip(self.f_hz, self.v_dbuv, self.limit_dbuv)
        ]


def prescan(v_in: float, i_out: float, filt: InputFilter | None = None,
            n_max: int = 80) -> PrescanResult:
    p = C.BUCK5
    r = rail("+5V")
    filt = filt or InputFilter()

    d = buck_duty(v_in, r.v_out_v, i_out, p["rds_hs_ohm"], p["rds_ls_ohm"],
                  p["L_dcr_ohm"])
    di = r.v_out_v * (1 - d) / (p["L_H"] * r.f_sw_hz)
    f, amps = trapezoid_harmonics(i_out - di / 2, i_out + di / 2, d, r.f_sw_hz,
                                  p["t_rise_s"], p["t_fall_s"], n_max)
    v = amps * filt.transfer_ohm(f)
    return PrescanResult(f, dbuv(v), en55032_class_b_qp_dbuv(f))


# --------------------------------------------------------------------------
# Input filter interaction
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MiddlebrookResult:
    f_hz: np.ndarray
    z_out_ohm: np.ndarray
    z_in_ohm: float
    v_in_v: float

    @property
    def peak_z_out_ohm(self) -> float:
        return float(np.max(self.z_out_ohm))

    @property
    def peak_f_hz(self) -> float:
        return float(self.f_hz[int(np.argmax(self.z_out_ohm))])

    @property
    def separation_db(self) -> float:
        return float(20 * np.log10(self.z_in_ohm / self.peak_z_out_ohm))


def middlebrook(v_in: float, p_in_w: float, filt: InputFilter | None = None,
                f_lo: float = 100.0, f_hi: float = 1e6) -> MiddlebrookResult:
    """Compare the filter output impedance with the converter input impedance.

    ``|Zin| = Vin^2 / Pin`` is the magnitude of the constant power load's
    incremental input resistance, valid below the control loop bandwidth. The
    usual rule of thumb asks for at least 6 dB of separation; this board is
    designed for more because the ESR that provides the damping is itself a
    loosely specified quantity that drifts with temperature and age.
    """
    filt = filt or InputFilter()
    f = np.logspace(np.log10(f_lo), np.log10(f_hi), 2001)
    return MiddlebrookResult(f, filt.z_out_ohm(f), v_in ** 2 / p_in_w, v_in)
