"""Compensator networks and the design procedure that picks their values.

Two networks are used on this board, deliberately:

Type II around a transconductance error amplifier, for the two peak current
mode loops. The current loop has already made the power stage look close to
first order, so one zero and one high frequency pole is all that is needed.

Type III around a voltage feedback error amplifier, for the voltage mode buck.
There the LC double pole eats 180 degrees of phase in one octave and two zeros
are needed to get it back.

The placement rules are written out in ``docs/compensation/*.md``. The gain
element is then solved for numerically so that the loop crosses over exactly
where the specification asks, and finally snapped to a stocked E series value
so that the reported margins are the ones the built board would have, not the
ones an infinite resolution resistor would have.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .analysis import margins

# --------------------------------------------------------------------------
# E series snapping
# --------------------------------------------------------------------------

E12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
       3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]
E96 = [round(10 ** (n / 96.0), 2) for n in range(96)]


def snap(value: float, series: list[float] = E24) -> float:
    """Nearest stocked value on a logarithmic scale."""
    if value <= 0:
        raise ValueError("value must be positive")
    decade = 10.0 ** np.floor(np.log10(value))
    mant = value / decade
    candidates = np.array(series + [series[0] * 10.0])
    best = candidates[np.argmin(np.abs(np.log(candidates) - np.log(mant)))]
    # Round to six significant figures so that a stocked value comes out as
    # 115 ohms rather than 114.99999999999999 in a generated CSV.
    return float(f"{best * decade:.6g}")


# --------------------------------------------------------------------------
# Type II, transconductance error amplifier
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TypeII:
    """``Gc(s) = Kdiv * gm * Z(s)`` with ``Z = ro || (Rc + 1/sCc) || 1/sCp``.

    ``ro`` is the error amplifier output resistance. Including it keeps the DC
    gain finite, which is what the real part does, and stops the reported DC
    loop gain being a meaningless infinity.
    """

    rc_ohm: float
    cc_f: float
    cp_f: float
    gm_s: float
    ro_ohm: float
    k_div: float

    def z(self, f_hz) -> np.ndarray:
        s = 2j * np.pi * np.atleast_1d(np.asarray(f_hz, dtype=float))
        y = 1.0 / self.ro_ohm + 1.0 / (self.rc_ohm + 1.0 / (s * self.cc_f)) + s * self.cp_f
        return 1.0 / y

    def response(self, f_hz) -> np.ndarray:
        return self.k_div * self.gm_s * self.z(f_hz)

    @property
    def f_zero_hz(self) -> float:
        return 1.0 / (2 * np.pi * self.rc_ohm * self.cc_f)

    @property
    def f_pole_hz(self) -> float:
        c = self.cc_f * self.cp_f / (self.cc_f + self.cp_f)
        return 1.0 / (2 * np.pi * self.rc_ohm * c)

    def values(self) -> dict:
        d = asdict(self)
        d["f_zero_hz"] = self.f_zero_hz
        d["f_pole_hz"] = self.f_pole_hz
        return d


# --------------------------------------------------------------------------
# Type III, voltage feedback error amplifier
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TypeIII:
    """Classic three resistor, three capacitor network round an op amp.

    ``Zf = (Rf + 1/sCf1) || 1/sCf2`` from COMP back to FB.
    ``Zi = R1 || (R3 + 1/sCf3)`` from Vout to FB.
    ``Gc(s) = Zf/Zi``, which already contains the feedback divider because R1
    *is* the top divider resistor. The bottom resistor sits on a virtual earth
    and does not appear in the small signal transfer.
    """

    r1_ohm: float
    rbot_ohm: float
    r3_ohm: float
    rf_ohm: float
    cf1_f: float
    cf2_f: float
    cf3_f: float
    #: Error amplifier open loop gain and gain bandwidth, for the finite gain
    #: correction. Set ``gbw_hz`` to ``inf`` for an ideal amplifier.
    a0_db: float = 80.0
    gbw_hz: float = 12e6

    def _zf(self, s):
        return 1.0 / (1.0 / (self.rf_ohm + 1.0 / (s * self.cf1_f)) + s * self.cf2_f)

    def _zi(self, s):
        return 1.0 / (1.0 / self.r1_ohm + 1.0 / (self.r3_ohm + 1.0 / (s * self.cf3_f)))

    def response(self, f_hz) -> np.ndarray:
        s = 2j * np.pi * np.atleast_1d(np.asarray(f_hz, dtype=float))
        ideal = self._zf(s) / self._zi(s)
        if not np.isfinite(self.gbw_hz):
            return ideal
        a0 = 10 ** (self.a0_db / 20.0)
        a = a0 / (1.0 + s * a0 / (2 * np.pi * self.gbw_hz))
        return ideal / (1.0 + (1.0 + ideal) / a)

    @property
    def f_zero1_hz(self) -> float:
        return 1.0 / (2 * np.pi * self.rf_ohm * self.cf1_f)

    @property
    def f_zero2_hz(self) -> float:
        return 1.0 / (2 * np.pi * (self.r1_ohm + self.r3_ohm) * self.cf3_f)

    @property
    def f_pole2_hz(self) -> float:
        c = self.cf1_f * self.cf2_f / (self.cf1_f + self.cf2_f)
        return 1.0 / (2 * np.pi * self.rf_ohm * c)

    @property
    def f_pole3_hz(self) -> float:
        return 1.0 / (2 * np.pi * self.r3_ohm * self.cf3_f)

    def values(self) -> dict:
        d = asdict(self)
        d.update(f_zero1_hz=self.f_zero1_hz, f_zero2_hz=self.f_zero2_hz,
                 f_pole2_hz=self.f_pole2_hz, f_pole3_hz=self.f_pole3_hz)
        return d


# --------------------------------------------------------------------------
# Plant feature detection
# --------------------------------------------------------------------------

def dominant_pole_hz(plant, f_lo: float = 1.0, f_hi: float = 1e6) -> float:
    """Frequency where a plant response is 3 dB below its low frequency value.

    Used to place the Type II zero on top of the current mode plant pole,
    which is the placement rule ``docs/compensation`` argues for.
    """
    f = np.logspace(np.log10(f_lo), np.log10(f_hi), 4001)
    mag = np.abs(plant(f))
    target = mag[0] / np.sqrt(2.0)
    below = np.where(mag <= target)[0]
    if len(below) == 0:
        return f_hi
    i = below[0]
    if i == 0:
        return f_lo
    lo, hi = np.log(f[i - 1]), np.log(f[i])
    y0, y1 = mag[i - 1], mag[i]
    t = (target - y0) / (y1 - y0)
    return float(np.exp(lo + t * (hi - lo)))


def resonance_hz(plant, f_lo: float = 100.0, f_hi: float = 1e6) -> float:
    """Frequency of the magnitude peak, i.e. the LC double pole."""
    f = np.logspace(np.log10(f_lo), np.log10(f_hi), 8001)
    return float(f[int(np.argmax(np.abs(plant(f))))])


# --------------------------------------------------------------------------
# Design procedures
# --------------------------------------------------------------------------

def design_type_ii(plant, f_cross_hz: float, f_zero_hz: float, f_pole_hz: float,
                   gm_s: float, ro_ohm: float, k_div: float,
                   snap_series: list[float] = E24,
                   snap_caps: list[float] = E12) -> TypeII:
    """Solve for Rc so the loop crosses at ``f_cross_hz``, then snap values.

    The zero and pole frequencies are held fixed while Rc moves, so Cc and Cp
    are rescaled with it. Two or three iterations are enough because the only
    nonlinearity is the shape of ``Z`` near the zero.
    """
    gp = complex(plant(np.array([f_cross_hz]))[0])
    rc = 1.0 / (k_div * gm_s * abs(gp))
    for _ in range(40):
        cc = 1.0 / (2 * np.pi * f_zero_hz * rc)
        cp = 1.0 / (2 * np.pi * f_pole_hz * rc)
        comp = TypeII(rc, cc, cp, gm_s, ro_ohm, k_div)
        gain = abs(comp.response(np.array([f_cross_hz]))[0] * gp)
        if abs(gain - 1.0) < 1e-9:
            break
        rc /= gain
    rc = snap(rc, snap_series)
    cc = snap(1.0 / (2 * np.pi * f_zero_hz * rc), snap_caps)
    cp = snap(1.0 / (2 * np.pi * f_pole_hz * rc), snap_caps)
    return TypeII(rc, cc, cp, gm_s, ro_ohm, k_div)


def design_type_iii(plant, f_cross_hz: float, f_zero_hz: float,
                    f_pole2_hz: float, f_pole3_hz: float,
                    v_out: float, v_ref: float, r1_ohm: float,
                    a0_db: float, gbw_hz: float,
                    snap_series: list[float] = E96,
                    snap_caps: list[float] = E24) -> TypeIII:
    """Place both zeros together at ``f_zero_hz``, both poles as given.

    R1 is fixed by the designer, R3 follows from the ratio of the second zero
    to the third pole, and Rf is solved for to set the crossover.
    """
    rbot = snap(r1_ohm * v_ref / (v_out - v_ref), snap_series)
    r3 = snap(r1_ohm / (f_pole3_hz / f_zero_hz - 1.0), snap_series)
    cf3 = snap(1.0 / (2 * np.pi * f_zero_hz * (r1_ohm + r3)), snap_caps)

    gp = complex(plant(np.array([f_cross_hz]))[0])
    rf = r1_ohm
    for _ in range(200):
        cf1 = 1.0 / (2 * np.pi * f_zero_hz * rf)
        # exact pole placement: 1/(2 pi Rf (Cf1 Cf2/(Cf1+Cf2))) = fp2
        denom = 2 * np.pi * f_pole2_hz * rf * cf1 - 1.0
        cf2 = cf1 / denom if denom > 0 else cf1 / 100.0
        comp = TypeIII(r1_ohm, rbot, r3, rf, cf1, cf2, cf3, a0_db, gbw_hz)
        gain = abs(comp.response(np.array([f_cross_hz]))[0] * gp)
        if abs(gain - 1.0) < 1e-9:
            break
        rf /= gain
    rf = snap(rf, snap_series)
    cf1 = snap(1.0 / (2 * np.pi * f_zero_hz * rf), snap_caps)
    denom = 2 * np.pi * f_pole2_hz * rf * cf1 - 1.0
    cf2 = snap(cf1 / denom, snap_caps)
    return TypeIII(r1_ohm, rbot, r3, rf, cf1, cf2, cf3, a0_db, gbw_hz)


def loop_margins(plant, comp, f: np.ndarray):
    """Margins of ``T = Gc * Gplant`` over the sweep ``f``."""
    return margins(f, comp.response(f) * plant(f))
