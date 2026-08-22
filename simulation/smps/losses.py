"""Loss model and efficiency prediction.

Every term is written out separately rather than folded into one fitted
efficiency curve, because the point of an efficiency plot on a design like this
is to say *where* the power goes, not just how much is left. The breakdown is
what tells you whether a bigger FET, a lower switching frequency or a different
inductor is the thing worth changing.

These are *predictions*. Nothing here has been measured. The terms most likely
to be wrong on a real board, in order, are: the switching loss overlap times,
which depend on gate drive strength and layout inductance and are the hardest
thing to estimate from a datasheet; the core loss, because the Steinmetz
coefficients are assumed rather than fitted to the real part; and Rds(on),
which rises roughly 40 percent from 25 to 100 degrees and is quoted here at
room temperature. ``docs/loss_model.md`` states the expected error band.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import components as C
from .sizing import boost_duty, buck_duty
from .spec import rail


@dataclass
class LossBreakdown:
    rail: str
    v_in_v: float
    i_out_a: float
    terms: dict = field(default_factory=dict)

    @property
    def total_w(self) -> float:
        return float(sum(self.terms.values()))

    @property
    def p_out_w(self) -> float:
        return self.v_out_v * self.i_out_a

    v_out_v: float = 0.0

    @property
    def efficiency(self) -> float:
        p_out = self.p_out_w
        return p_out / (p_out + self.total_w) if p_out > 0 else 0.0

    def row(self) -> dict:
        d = {"rail": self.rail, "v_in_v": round(self.v_in_v, 3),
             "i_out_a": round(self.i_out_a, 4),
             "p_out_w": round(self.p_out_w, 4)}
        d.update({k: round(v, 5) for k, v in self.terms.items()})
        d["p_loss_total_w"] = round(self.total_w, 5)
        d["efficiency_pct"] = round(100 * self.efficiency, 3)
        return d


def _rms_sq(i_avg: float, i_ripple_pp: float) -> float:
    """Mean square of a DC level with a triangular ripple on top."""
    return i_avg ** 2 + i_ripple_pp ** 2 / 12.0


def core_loss_w(p: dict, i_ripple_pp: float) -> float:
    """Steinmetz core loss from the peak AC flux density.

    ``B_ac = L * dI/2 / (N * Ae)``, then ``Pv = k f^alpha B^beta`` in W/m^3.
    """
    b_ac = p["L_H"] * (i_ripple_pp / 2.0) / (p["core_n_turns"] * p["core_ae_m2"])
    return 0.0 if b_ac <= 0 else (
        p["core_k"] * p["f_sw_hz"] ** p["core_alpha"] * b_ac ** p["core_beta"]
        * p["core_ve_m3"]
    )


# --------------------------------------------------------------------------
# Buck
# --------------------------------------------------------------------------

def buck_losses(rail_name: str, p: dict, v_in: float, i_out: float,
                controller_quiescent_w: float) -> LossBreakdown:
    r = rail(rail_name)
    v_out = r.v_out_v
    f_sw = r.f_sw_hz
    p = dict(p, f_sw_hz=f_sw)

    d = buck_duty(v_in, v_out, i_out, p["rds_hs_ohm"], p["rds_ls_ohm"], p["L_dcr_ohm"])
    d = min(max(d, 1e-4), 0.99)
    di = v_out * (1.0 - d) / (p["L_H"] * f_sw)
    i_sq = _rms_sq(i_out, di)

    terms = {
        "hs_conduction_w": d * i_sq * p["rds_hs_ohm"],
        "ls_conduction_w": (1.0 - d) * i_sq * p["rds_ls_ohm"],
        "inductor_dcr_w": i_sq * p["L_dcr_ohm"],
        "inductor_core_w": core_loss_w(p, di),
        # Hard switched turn on and turn off of the high side device.
        "hs_switching_w": 0.5 * v_in * i_out * (p["t_rise_s"] + p["t_fall_s"]) * f_sw,
        "output_charge_w": p["qoss_hs_c"] * v_in * f_sw,
        "gate_drive_w": (p["qg_hs_c"] + p["qg_ls_c"]) * p["vgs_drive_v"] * f_sw,
        # Body diode conducts for both dead time intervals every cycle.
        "dead_time_w": p["vf_body_v"] * i_out * 2.0 * p["t_dead_s"] * f_sw,
        "cout_esr_w": (di ** 2 / 12.0) * p["Cout_esr_ohm"],
        "cin_esr_w": (i_out ** 2 * d * (1.0 - d)) * p["Cin_esr_ohm"],
        "controller_w": controller_quiescent_w,
    }
    return LossBreakdown(rail_name, v_in, i_out, terms, v_out_v=v_out)


# --------------------------------------------------------------------------
# Boost
# --------------------------------------------------------------------------

def boost_losses(rail_name: str, p: dict, v_in: float, i_out: float,
                 controller_quiescent_w: float) -> LossBreakdown:
    r = rail(rail_name)
    v_out = r.v_out_v
    f_sw = r.f_sw_hz
    p = dict(p, f_sw_hz=f_sw)

    d = boost_duty(v_in, v_out, i_out, p["rds_lo_ohm"], p["rds_hi_ohm"], p["L_dcr_ohm"])
    d = min(max(d, 1e-4), 0.9)
    i_l = i_out / (1.0 - d)
    di = v_in * d / (p["L_H"] * f_sw)
    i_sq = _rms_sq(i_l, di)

    terms = {
        "lo_conduction_w": d * i_sq * p["rds_lo_ohm"],
        "hi_conduction_w": (1.0 - d) * i_sq * p["rds_hi_ohm"],
        "inductor_dcr_w": i_sq * p["L_dcr_ohm"],
        "inductor_core_w": core_loss_w(p, di),
        "switching_w": 0.5 * v_out * i_l * (p["t_rise_s"] + p["t_fall_s"]) * f_sw,
        "output_charge_w": p["qoss_hi_c"] * v_out * f_sw,
        "gate_drive_w": (p["qg_lo_c"] + p["qg_hi_c"]) * p["vgs_drive_v"] * f_sw,
        "dead_time_w": p["vf_body_v"] * i_l * 2.0 * p["t_dead_s"] * f_sw,
        "cout_esr_w": (i_out ** 2 * d / max(1.0 - d, 1e-3)) * p["Cout_esr_ohm"],
        "cin_esr_w": (di ** 2 / 12.0) * p["Cin_esr_ohm"],
        "controller_w": controller_quiescent_w,
    }
    return LossBreakdown(rail_name, v_in, i_out, terms, v_out_v=v_out)


# --------------------------------------------------------------------------
# LDO
# --------------------------------------------------------------------------

def ldo_losses(v_in: float, i_out: float) -> LossBreakdown:
    r = rail("+1V8A")
    p = C.LDO1V8
    i_preload = r.v_out_v / p["preload_r_ohm"]
    i_total = i_out + i_preload
    v_after_filter = v_in - p["input_rc_r_ohm"] * i_total
    terms = {
        "input_filter_w": p["input_rc_r_ohm"] * i_total ** 2,
        "pass_device_w": (v_after_filter - r.v_out_v) * i_total,
        "preload_w": r.v_out_v * i_preload,
        "quiescent_w": v_in * p["iq_a"],
    }
    return LossBreakdown("+1V8A", v_in, i_out, terms, v_out_v=r.v_out_v)


# --------------------------------------------------------------------------
# Per rail entry points and the whole power tree
# --------------------------------------------------------------------------

CONTROLLER_QUIESCENT_W = {"+5V": 8e-3, "+3V3": 5e-3, "+12V": 4e-3}


def rail_losses(rail_name: str, v_in: float, i_out: float) -> LossBreakdown:
    if rail_name == "+5V":
        return buck_losses("+5V", C.BUCK5, v_in, i_out, CONTROLLER_QUIESCENT_W["+5V"])
    if rail_name == "+3V3":
        return buck_losses("+3V3", C.BUCK3V3, v_in, i_out, CONTROLLER_QUIESCENT_W["+3V3"])
    if rail_name == "+12V":
        return boost_losses("+12V", C.BOOST12, v_in, i_out, CONTROLLER_QUIESCENT_W["+12V"])
    if rail_name == "+1V8A":
        return ldo_losses(v_in, i_out)
    raise KeyError(rail_name)


@dataclass
class PowerTree:
    v_in_v: float
    per_rail: dict
    i_in_a: float
    p_in_w: float
    p_useful_w: float

    @property
    def efficiency(self) -> float:
        return self.p_useful_w / self.p_in_w if self.p_in_w > 0 else 0.0

    @property
    def total_loss_w(self) -> float:
        return self.p_in_w - self.p_useful_w


def solve_power_tree(v_in: float, load_fraction: float = 1.0) -> PowerTree:
    """Work backwards from the leaves so each rail sees its real load.

    The 3V3 buck feeds the 1V8 LDO, and the 5V buck feeds both the 3V3 buck and
    the 12V boost, so the 5V stage carries far more current than its connector
    rating suggests. Doing this by hand is where a power budget usually goes
    wrong, so it is done by code and asserted in ``tests/test_losses.py``.
    """
    r5, r3, r12, r18 = (rail("+5V"), rail("+3V3"), rail("+12V"), rail("+1V8A"))

    i_18 = r18.i_external_a * load_fraction
    l18 = ldo_losses(r3.v_out_v, i_18)
    i_3v3_total = (i_18 + r18.v_out_v / C.LDO1V8["preload_r_ohm"]
                   + C.LDO1V8["iq_a"] + r3.i_external_a * load_fraction)
    l3 = rail_losses("+3V3", r5.v_out_v, i_3v3_total)

    i_12 = r12.i_external_a * load_fraction
    l12 = rail_losses("+12V", r5.v_out_v, i_12)

    i_5v_total = (
        r5.i_external_a * load_fraction
        + (l3.p_out_w + l3.total_w) / r5.v_out_v
        + (l12.p_out_w + l12.total_w) / r5.v_out_v
    )
    l5 = rail_losses("+5V", v_in, i_5v_total)

    p_in = l5.p_out_w + l5.total_w
    p_useful = (
        r5.v_out_v * r5.i_external_a * load_fraction
        + r3.v_out_v * r3.i_external_a * load_fraction
        + r12.v_out_v * r12.i_external_a * load_fraction
        + r18.v_out_v * i_18
    )
    return PowerTree(
        v_in_v=v_in,
        per_rail={"+5V": l5, "+3V3": l3, "+12V": l12, "+1V8A": l18},
        i_in_a=p_in / v_in, p_in_w=p_in, p_useful_w=p_useful,
    )


def efficiency_curve(rail_name: str, v_in: float,
                     points: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """Efficiency against load for one stage in isolation."""
    r = rail(rail_name)
    i = np.logspace(np.log10(0.02 * r.i_max_a), np.log10(r.i_max_a), points)
    eta = np.array([rail_losses(rail_name, v_in, float(x)).efficiency for x in i])
    return i, eta


def system_efficiency_curve(v_in: float, points: int = 20):
    frac = np.linspace(0.05, 1.0, points)
    out = [solve_power_tree(v_in, float(f)) for f in frac]
    return frac, np.array([t.efficiency for t in out]), out
