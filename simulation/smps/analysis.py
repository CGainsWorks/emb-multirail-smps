"""Frequency response bookkeeping: crossover, phase margin, gain margin.

Kept separate from the models so that a loop gain measured from the switching
simulator and a loop gain evaluated from the analytic model go through exactly
the same reduction. If the two disagree it is the physics that differs, not the
way the margins were extracted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LoopMargins:
    f_cross_hz: float
    phase_margin_deg: float
    gain_margin_db: float
    f_180_hz: float
    dc_gain_db: float

    def as_row(self, name: str) -> dict:
        return {
            "loop": name,
            "f_crossover_hz": round(self.f_cross_hz, 1),
            "phase_margin_deg": round(self.phase_margin_deg, 2),
            "gain_margin_db": round(self.gain_margin_db, 2),
            "f_at_minus180_hz": (round(self.f_180_hz, 1)
                                 if np.isfinite(self.f_180_hz) else "none below fsw/2"),
            "dc_gain_db": round(self.dc_gain_db, 2),
        }


def db(x) -> np.ndarray:
    return 20.0 * np.log10(np.abs(np.asarray(x)))


def phase_deg(x) -> np.ndarray:
    return np.degrees(np.unwrap(np.angle(np.asarray(x))))


def _interp_cross(f: np.ndarray, y: np.ndarray, level: float, i: int) -> float:
    """Log frequency interpolation of the crossing between i and i+1."""
    y0, y1 = y[i], y[i + 1]
    if y1 == y0:
        return float(f[i])
    t = (level - y0) / (y1 - y0)
    return float(np.exp(np.log(f[i]) + t * (np.log(f[i + 1]) - np.log(f[i]))))


def margins(f: np.ndarray, t: np.ndarray) -> LoopMargins:
    """Crossover, phase margin and gain margin of a loop gain ``t`` over ``f``.

    Crossover is the last downward crossing of unity gain, which is the one
    that matters when a loop gain dips near 0 dB more than once.
    """
    f = np.asarray(f, dtype=float)
    mag = db(t)
    pha = phase_deg(t)

    down = [i for i in range(len(f) - 1) if mag[i] > 0.0 >= mag[i + 1]]
    if not down:
        raise ValueError("loop gain never crosses 0 dB in the swept range")
    i = down[-1]
    fc = _interp_cross(f, mag, 0.0, i)
    pm = 180.0 + float(np.interp(np.log(fc), np.log(f), pha))

    # Gain margin: first crossing of -180 degrees above crossover.
    f_180 = np.inf
    gm = np.inf
    idx = [j for j in range(len(f) - 1)
           if f[j] >= fc and ((pha[j] + 180.0) * (pha[j + 1] + 180.0) <= 0.0)
           and pha[j] != pha[j + 1]]
    if idx:
        j = idx[0]
        f_180 = _interp_cross(f, pha, -180.0, j)
        gm = -float(np.interp(np.log(f_180), np.log(f), mag))

    return LoopMargins(fc, pm, gm, f_180, float(mag[0]))


def log_sweep(f_start: float, f_stop: float, points_per_decade: int = 60) -> np.ndarray:
    n = int(round(points_per_decade * np.log10(f_stop / f_start))) + 1
    return np.logspace(np.log10(f_start), np.log10(f_stop), n)
