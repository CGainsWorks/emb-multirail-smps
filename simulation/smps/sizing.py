"""Power stage sizing, worked from the specification.

Each function returns both the *required* value from the spec and the *chosen*
value from :mod:`smps.components`, so a test can assert the choice actually
satisfies the requirement rather than trusting a comment.

The formulae are the standard continuous conduction mode results. They are
derived, with the arithmetic for this board written out, in
``docs/design_notes.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import components as C
from .spec import SYSTEM, rail


@dataclass(frozen=True)
class SizingResult:
    quantity: str
    unit: str
    required: float
    chosen: float
    #: True when ``chosen`` satisfying the requirement means chosen >= required.
    higher_is_better: bool
    note: str = ""

    @property
    def ok(self) -> bool:
        if self.higher_is_better:
            return self.chosen >= self.required * (1 - 1e-9)
        return self.chosen <= self.required * (1 + 1e-9)

    @property
    def margin_pct(self) -> float:
        if self.required == 0:
            return math.inf
        if self.higher_is_better:
            return 100.0 * (self.chosen - self.required) / self.required
        return 100.0 * (self.required - self.chosen) / self.required


# --------------------------------------------------------------------------
# Duty ratio helpers, including conduction drops
# --------------------------------------------------------------------------

def buck_duty(vin: float, vout: float, iout: float, rds_hs: float,
              rds_ls: float, rdcr: float) -> float:
    """Buck duty ratio including switch and inductor resistive drops.

    Solving ``Vout = D*Vin - Iout*(D*Rhs + (1-D)*Rls + Rdcr)`` for D.
    """
    num = vout + iout * (rds_ls + rdcr)
    den = vin - iout * (rds_hs - rds_ls)
    return num / den


def boost_duty(vin: float, vout: float, iout: float, rds_lo: float,
               rds_hi: float, rdcr: float) -> float:
    """Boost duty ratio including resistive drops, solved iteratively.

    ``Vin = Vout*(1-D) + IL*(D*Rlo + (1-D)*Rhi + Rdcr)`` with ``IL = Iout/(1-D)``.
    """
    d = 1.0 - vin / vout
    for _ in range(80):
        il = iout / max(1.0 - d, 1e-3)
        loss = il * (d * rds_lo + (1.0 - d) * rds_hi + rdcr)
        d_new = 1.0 - (vin - loss) / vout
        d = 0.5 * d + 0.5 * d_new
    return d


def buck_ripple_current(vin: float, vout: float, l_h: float, f_sw: float) -> float:
    d = vout / vin
    return vout * (1.0 - d) / (l_h * f_sw)


def boost_ripple_current(vin: float, vout: float, l_h: float, f_sw: float) -> float:
    d = 1.0 - vin / vout
    return vin * d / (l_h * f_sw)


# --------------------------------------------------------------------------
# Per rail sizing
# --------------------------------------------------------------------------

def size_buck5() -> list[SizingResult]:
    r = rail("+5V")
    p = C.BUCK5
    out: list[SizingResult] = []

    # Inductor: sized for 30 % ripple at the worst case, which for a buck is
    # maximum input voltage (minimum duty).
    ripple_target = r.ripple_ratio * r.i_max_a
    d_max_vin = r.v_out_v / SYSTEM.vin_max_v
    l_req = r.v_out_v * (1.0 - d_max_vin) / (ripple_target * r.f_sw_hz)
    out.append(SizingResult("L, +5V buck", "H", l_req, p["L_H"], True,
                            f"{r.ripple_ratio:.0%} ripple at Vin(max) = 36 V"))

    di = buck_ripple_current(SYSTEM.vin_max_v, r.v_out_v, p["L_H"], r.f_sw_hz)
    i_peak = r.i_max_a + di / 2.0
    out.append(SizingResult("Inductor Isat headroom, +5V", "A", i_peak, p["L_isat_a"], True,
                            f"peak = Iout + dI/2 = {i_peak:.3f} A"))

    # Output capacitance for ripple. Split the budget: 60 % capacitive,
    # the remainder covers ESR and layout.
    v_cap_budget = 0.60 * r.v_ripple_max_vpp
    c_req = di / (8.0 * r.f_sw_hz * v_cap_budget)
    out.append(SizingResult("Cout, +5V buck", "F", c_req, p["Cout_F"], True,
                            "capacitive share of the ripple budget"))

    v_ripple = di / (8.0 * r.f_sw_hz * p["Cout_F"]) + di * p["Cout_esr_ohm"]
    out.append(SizingResult("Output ripple, +5V", "Vpp", r.v_ripple_max_vpp, v_ripple, False,
                            "capacitive plus ESR, steady state"))

    # Transient: the deviation with a first order loop is set by the output
    # capacitor and the crossover frequency.
    dv = r.load_step_a / (2.0 * math.pi * r.f_cross_target_hz * p["Cout_F"])
    out.append(SizingResult("Load step deviation, +5V", "V", r.v_deviation_max_v, dv, False,
                            f"dI/(2*pi*fc*Cout) at fc = {r.f_cross_target_hz/1e3:.0f} kHz"))

    return out


def size_buck3v3() -> list[SizingResult]:
    r = rail("+3V3")
    p = C.BUCK3V3
    vin = rail("+5V").v_out_v
    out: list[SizingResult] = []

    ripple_target = r.ripple_ratio * r.i_max_a
    d = r.v_out_v / vin
    l_req = r.v_out_v * (1.0 - d) / (ripple_target * r.f_sw_hz)
    out.append(SizingResult("L, +3V3 buck", "H", l_req, p["L_H"], True,
                            f"{r.ripple_ratio:.0%} ripple, fixed 5 V input"))

    di = buck_ripple_current(vin, r.v_out_v, p["L_H"], r.f_sw_hz)
    i_peak = r.i_max_a + di / 2.0
    out.append(SizingResult("Inductor Isat headroom, +3V3", "A", i_peak, p["L_isat_a"], True,
                            f"peak = {i_peak:.3f} A"))

    v_cap_budget = 0.60 * r.v_ripple_max_vpp
    c_req = di / (8.0 * r.f_sw_hz * v_cap_budget)
    out.append(SizingResult("Cout, +3V3 buck", "F", c_req, p["Cout_F"], True, ""))

    v_ripple = di / (8.0 * r.f_sw_hz * p["Cout_F"]) + di * p["Cout_esr_ohm"]
    out.append(SizingResult("Output ripple, +3V3", "Vpp", r.v_ripple_max_vpp, v_ripple, False, ""))

    dv = r.load_step_a / (2.0 * math.pi * r.f_cross_target_hz * p["Cout_F"])
    out.append(SizingResult("Load step deviation, +3V3", "V", r.v_deviation_max_v, dv, False, ""))

    # Voltage mode needs the LC double pole well below crossover.
    f_lc = 1.0 / (2.0 * math.pi * math.sqrt(p["L_H"] * p["Cout_F"]))
    out.append(SizingResult("fc / f_LC ratio, +3V3", "-", 3.0,
                            r.f_cross_target_hz / f_lc, True,
                            f"f_LC = {f_lc/1e3:.2f} kHz, needs enough separation for Type III"))
    return out


def size_boost12() -> list[SizingResult]:
    r = rail("+12V")
    p = C.BOOST12
    vin = rail("+5V").v_out_v
    out: list[SizingResult] = []

    d = 1.0 - vin / r.v_out_v
    i_l = r.i_max_a / (1.0 - d)
    ripple_target = r.ripple_ratio * i_l
    l_req = vin * d / (ripple_target * r.f_sw_hz)
    out.append(SizingResult("L, +12V boost", "H", l_req, p["L_H"], True,
                            f"{r.ripple_ratio:.0%} of IL = {i_l:.3f} A, "
                            "raised from 30 % to keep the RHP zero high"))

    di = boost_ripple_current(vin, r.v_out_v, p["L_H"], r.f_sw_hz)
    i_peak = i_l + di / 2.0
    out.append(SizingResult("Inductor Isat headroom, +12V", "A", i_peak, p["L_isat_a"], True,
                            f"peak = {i_peak:.3f} A"))

    # Boost output ripple is dominated by the capacitor supplying the load for
    # the whole on time.
    v_cap_budget = 0.60 * r.v_ripple_max_vpp
    c_req = r.i_max_a * d / (r.f_sw_hz * v_cap_budget)
    out.append(SizingResult("Cout, +12V boost", "F", c_req, p["Cout_F"], True, ""))

    v_ripple = r.i_max_a * d / (r.f_sw_hz * p["Cout_F"]) + i_peak * p["Cout_esr_ohm"]
    out.append(SizingResult("Output ripple, +12V", "Vpp", r.v_ripple_max_vpp, v_ripple, False, ""))

    # Right half plane zero. Crossover has to sit well below it.
    f_rhpz = (1.0 - d) ** 2 * (r.v_out_v / r.i_max_a) / (2.0 * math.pi * p["L_H"])
    out.append(SizingResult("f_RHPZ / fc ratio, +12V", "-", 5.0,
                            f_rhpz / r.f_cross_target_hz, True,
                            f"f_RHPZ = {f_rhpz/1e3:.2f} kHz at full load"))

    dv = r.load_step_a / (2.0 * math.pi * r.f_cross_target_hz * p["Cout_F"])
    out.append(SizingResult("Load step deviation, +12V", "V", r.v_deviation_max_v, dv, False, ""))
    return out


def size_ldo1v8() -> list[SizingResult]:
    r = rail("+1V8A")
    p = C.LDO1V8
    src = rail("+3V3")
    out: list[SizingResult] = []

    i_total = r.i_max_a + r.v_out_v / p["preload_r_ohm"]
    v_filter_drop = p["input_rc_r_ohm"] * i_total
    headroom = (src.v_out_v * (1 - src.v_tol_pct / 100.0)
                - v_filter_drop - r.v_out_v)
    out.append(SizingResult("Dropout headroom, +1V8A", "V", p["dropout_v_at_imax"],
                            headroom, True,
                            f"worst case 3V3 low, less {v_filter_drop*1e3:.0f} mV "
                            "across the input filter resistor"))

    p_diss = (src.v_out_v - r.v_out_v) * r.i_max_a
    out.append(SizingResult("LDO dissipation, +1V8A", "W", 1.0, p_diss, False,
                            "package limit assumption, confirm with the real thermal pad"))
    return out


def all_sizing() -> list[SizingResult]:
    return size_buck5() + size_buck3v3() + size_boost12() + size_ldo1v8()


def f_rhpz_hz(iout: float | None = None) -> float:
    """Boost right half plane zero frequency at a given load."""
    r = rail("+12V")
    p = C.BOOST12
    iout = r.i_max_a if iout is None else iout
    vin = rail("+5V").v_out_v
    d = 1.0 - vin / r.v_out_v
    r_load = r.v_out_v / max(iout, 1e-6)
    return (1.0 - d) ** 2 * r_load / (2.0 * math.pi * p["L_H"])
