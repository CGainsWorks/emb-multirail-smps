"""Everything the switching simulator is asked to produce, in one place.

Each function returns plain data. :mod:`smps.plots` draws it and
:mod:`smps.report` writes it up, so the numbers in the plots, the CSVs and the
report cannot disagree with each other.

Every result in this module is *simulated*. The directory it lands in is called
``test-results`` because that is the layout the project brief asks for, not
because anything was tested on hardware. ``STATUS.md`` is unambiguous about
this and so is every plot title.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import design as D
from .analysis import LoopMargins, log_sweep, margins
from .emc import middlebrook, prescan
from .losses import (efficiency_curve, rail_losses, solve_power_tree,
                     system_efficiency_curve)
from .loopmeas import linearity_check, measure_loop
from .sizing import all_sizing
from .spec import SYSTEM, rail
from .switching import ConverterSim
from .thermal import derating_curve, max_ambient_c, solve_thermal

SWITCHED_RAILS = ("+5V", "+3V3", "+12V")

#: Sweep limits for the switching simulator, per rail. The upper limit is kept
#: below fsw/2 because a once-per-cycle sampler cannot see past its own Nyquist
#: frequency, exactly like a real analyser triggered off the switching clock.
SIM_SWEEP = {
    "+5V": (1e3, 210e3, 28),
    "+3V3": (2e3, 420e3, 28),
    "+12V": (2e2, 160e3, 26),
}


# numpy 2 renamed trapz to trapezoid and deprecated the old spelling. Support
# both so the same source runs on the whole supported Python range.
_trapezoid = getattr(np, "trapezoid", None) or np.trapz


def _time_mean(t: np.ndarray, v: np.ndarray) -> float:
    """Time weighted mean, because the simulator's samples are not evenly
    spaced: sub-steps inside the on interval are shorter than those inside the
    off interval whenever the duty ratio is not exactly a half."""
    return float(_trapezoid(v, t) / (t[-1] - t[0]))


# --------------------------------------------------------------------------
# Loop gain: analytic against simulated
# --------------------------------------------------------------------------

@dataclass
class LoopComparison:
    rail: str
    f_sim: np.ndarray
    t_sim: np.ndarray
    f_ana: np.ndarray
    t_ana: np.ndarray
    m_sim: LoopMargins
    m_ana: LoopMargins
    linearity: float

    @property
    def f_cross_error_pct(self) -> float:
        return 100.0 * (self.m_sim.f_cross_hz / self.m_ana.f_cross_hz - 1.0)

    @property
    def pm_error_deg(self) -> float:
        return self.m_sim.phase_margin_deg - self.m_ana.phase_margin_deg

    def row(self) -> dict:
        r = rail(self.rail)
        return {
            "rail": self.rail,
            "f_cross_target_hz": r.f_cross_target_hz,
            "f_cross_hand_hz": round(self.m_ana.f_cross_hz, 1),
            "f_cross_sim_hz": round(self.m_sim.f_cross_hz, 1),
            "f_cross_error_pct": round(self.f_cross_error_pct, 2),
            "pm_target_deg": r.phase_margin_target_deg,
            "pm_hand_deg": round(self.m_ana.phase_margin_deg, 2),
            "pm_sim_deg": round(self.m_sim.phase_margin_deg, 2),
            "pm_error_deg": round(self.pm_error_deg, 2),
            "gm_hand_db": round(self.m_ana.gain_margin_db, 2),
            "gm_sim_db": (round(self.m_sim.gain_margin_db, 2)
                          if np.isfinite(self.m_sim.gain_margin_db)
                          else "no -180 deg crossing below fsw/2"),
            "injection_linearity_rel": f"{self.linearity:.2e}",
        }


def loop_comparison(rail_name: str) -> LoopComparison:
    op = D.design_point(rail_name)
    cfg = D.sim_config(rail_name, op)
    f_lo, f_hi, n = SIM_SWEEP[rail_name]
    f_sim, t_sim = measure_loop(cfg, f_lo, f_hi, points=n)
    # The analytic model is swept to fsw/2, which is as far as the Ridley
    # sampled data model claims to be valid. The switching measurement stops
    # a little short of that because a once-per-cycle sampler cannot go there.
    f_ana = log_sweep(f_lo, 0.5 * rail(rail_name).f_sw_hz, 150)
    t_ana = D.analytic_loop(rail_name, op)(f_ana)
    m_sim = margins(f_sim, t_sim)
    m_ana = margins(f_ana, t_ana)
    lin = linearity_check(cfg, m_sim.f_cross_hz)
    return LoopComparison(rail_name, f_sim, t_sim, f_ana, t_ana, m_sim, m_ana, lin)


def all_loop_comparisons() -> list[LoopComparison]:
    return [loop_comparison(r) for r in SWITCHED_RAILS]


# --------------------------------------------------------------------------
# Steady state: ripple, load regulation, line regulation
# --------------------------------------------------------------------------

def steady_state(rail_name: str, v_in: float, i_out: float,
                 cycles: int = 2500) -> tuple[float, float]:
    """Settled mean output voltage and peak to peak ripple."""
    op = D.OperatingPoint(f"{v_in} V, {i_out} A", v_in, i_out)
    cfg = D.sim_config(rail_name, op)
    sim = ConverterSim(cfg)
    u = np.array([cfg.v_in, 0.0, cfg.v_target])
    res = sim.run(cycles, lambda _k: u, samples_per_interval=16,
                  dense_from_cycle=cycles - 12)
    tail = res.t > res.t[-1] - 6.0 / cfg.f_sw
    v = res.v_out[tail]
    t = res.t[tail]
    return _time_mean(t, v), float(v.max() - v.min())


def load_regulation_rows() -> list[dict]:
    rows: list[dict] = []
    for rail_name in SWITCHED_RAILS:
        r = rail(rail_name)
        v_in = SYSTEM.vin_nom_v if rail_name == "+5V" else rail("+5V").v_out_v
        loads = np.array([0.05, 0.25, 0.5, 0.75, 1.0]) * r.i_max_a
        nominal = None
        for i in loads:
            v, ripple = steady_state(rail_name, v_in, float(i))
            if nominal is None:
                nominal = v
            rows.append({
                "rail": rail_name, "v_in_v": round(v_in, 3),
                "i_out_a": round(float(i), 4),
                "v_out_v": round(v, 6),
                # Three decimals, not four. The solver resolves a settled
                # output voltage to about 1 ppm, which is 0.0001 percent, so a
                # fourth decimal here would be reporting its own noise.
                "deviation_from_light_load_pct": round(100 * (v / nominal - 1), 3),
                "ripple_mvpp": round(1e3 * ripple, 3),
                "ripple_limit_mvpp": round(1e3 * r.v_ripple_max_vpp, 3),
            })
    return rows


def line_regulation_rows() -> list[dict]:
    rows: list[dict] = []
    r = rail("+5V")
    nominal = None
    for v_in in (8.0, 12.0, 18.0, 24.0, 30.0, 36.0):
        v, ripple = steady_state("+5V", v_in, r.i_max_a)
        if nominal is None:
            nominal = v
        rows.append({
            "rail": "+5V", "v_in_v": v_in, "i_out_a": r.i_max_a,
            "v_out_v": round(v, 6),
            "deviation_from_8v_pct": round(100 * (v / nominal - 1), 3),
            "ripple_mvpp": round(1e3 * ripple, 3),
        })
    # The downstream rails see a regulated 5 V, so their line test is the
    # tolerance band of that rail rather than the whole 8 to 36 V range.
    for rail_name in ("+3V3", "+12V"):
        rr = rail(rail_name)
        nominal = None
        for v_in in (4.95, 5.0, 5.05):
            v, ripple = steady_state(rail_name, v_in, rr.i_max_a)
            if nominal is None:
                nominal = v
            rows.append({
                "rail": rail_name, "v_in_v": v_in, "i_out_a": rr.i_max_a,
                "v_out_v": round(v, 6),
                "deviation_from_8v_pct": round(100 * (v / nominal - 1), 3),
                "ripple_mvpp": round(1e3 * ripple, 3),
            })
    return rows


# --------------------------------------------------------------------------
# Load transient
# --------------------------------------------------------------------------

@dataclass
class TransientResult:
    rail: str
    t_us: np.ndarray
    v_out: np.ndarray
    v_settled: float
    undershoot_mv: float
    overshoot_mv: float
    settle_time_us: float
    step_a: float

    def row(self) -> dict:
        r = rail(self.rail)
        return {
            "rail": self.rail,
            "step_a": self.step_a,
            "undershoot_mv": round(self.undershoot_mv, 2),
            "overshoot_mv": round(self.overshoot_mv, 2),
            "limit_mv": round(1e3 * r.v_deviation_max_v, 2),
            "settle_time_us": round(self.settle_time_us, 2),
            "settle_limit_us": round(1e6 * r.settle_time_max_s, 2),
        }


def load_transient(rail_name: str, cycles_before: int = 1500,
                   cycles_after: int = 2500) -> TransientResult:
    """Step the load with a current source, the way an electronic load does."""
    r = rail(rail_name)
    v_in = SYSTEM.vin_nom_v if rail_name == "+5V" else rail("+5V").v_out_v
    i_base = r.i_max_a - r.load_step_a
    op = D.OperatingPoint("transient", v_in, i_base)
    cfg = D.sim_config(rail_name, op)
    sim = ConverterSim(cfg)

    u_lo = np.array([cfg.v_in, 0.0, cfg.v_target])
    u_hi = np.array([cfg.v_in, r.load_step_a, cfg.v_target])

    res = sim.run(cycles_before + cycles_after,
                  lambda k: u_lo if k < cycles_before else u_hi,
                  samples_per_interval=12,
                  dense_from_cycle=cycles_before - 40)
    t0 = cycles_before / cfg.f_sw
    pre = res.t < t0
    post = res.t >= t0
    v_pre = _time_mean(res.t[pre][-200:], res.v_out[pre][-200:])
    tail = res.t > res.t[-1] - 20.0 / cfg.f_sw
    v_settled = _time_mean(res.t[tail], res.v_out[tail])

    v_post = res.v_out[post]
    t_post = res.t[post] - t0
    undershoot = (v_pre - v_post.min()) * 1e3
    overshoot = (v_post.max() - v_pre) * 1e3

    # Settling: last time the envelope leaves a band of one percent of the
    # nominal output around the final value.
    band = 0.01 * r.v_out_v
    outside = np.where(np.abs(v_post - v_settled) > band)[0]
    settle_us = 1e6 * float(t_post[outside[-1]]) if outside.size else 0.0

    return TransientResult(rail_name, 1e6 * (res.t - t0), res.v_out, v_settled,
                           undershoot, overshoot, settle_us, r.load_step_a)


# --------------------------------------------------------------------------
# Efficiency, thermal, EMC
# --------------------------------------------------------------------------

def efficiency_rows() -> list[dict]:
    rows: list[dict] = []
    for rail_name in ("+5V", "+3V3", "+12V", "+1V8A"):
        r = rail(rail_name)
        v_in = SYSTEM.vin_nom_v if rail_name == "+5V" else (
            rail("+5V").v_out_v if rail_name != "+1V8A" else rail("+3V3").v_out_v)
        for frac in (0.05, 0.1, 0.25, 0.5, 0.75, 1.0):
            rows.append(rail_losses(rail_name, v_in, frac * r.i_max_a).row())
    return rows


def system_efficiency_rows() -> list[dict]:
    rows: list[dict] = []
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        for frac in (0.1, 0.25, 0.5, 0.75, 1.0):
            t = solve_power_tree(v_in, frac)
            rows.append({
                "v_in_v": v_in, "load_fraction": frac,
                "p_in_w": round(t.p_in_w, 4), "i_in_a": round(t.i_in_a, 4),
                "p_useful_w": round(t.p_useful_w, 4),
                "p_loss_w": round(t.total_loss_w, 4),
                "efficiency_pct": round(100 * t.efficiency, 3),
            })
    return rows


def thermal_rows() -> list[dict]:
    rows: list[dict] = []
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        res = solve_thermal(v_in, SYSTEM.ambient_max_c)
        for r in res.rows():
            r["v_in_v"] = v_in
            r["t_ambient_c"] = SYSTEM.ambient_max_c
            rows.append(r)
    return rows


def emc_rows() -> list[dict]:
    rows: list[dict] = []
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        res = prescan(v_in, solve_power_tree(v_in).per_rail["+5V"].i_out_a)
        for r in res.rows():
            r["v_in_v"] = v_in
            rows.append(r)
    return rows


def emc_summary_rows() -> list[dict]:
    rows: list[dict] = []
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        tree = solve_power_tree(v_in)
        res = prescan(v_in, tree.per_rail["+5V"].i_out_a)
        mb = middlebrook(v_in, tree.p_in_w)
        rows.append({
            "v_in_v": v_in,
            "worst_margin_db": round(res.worst_margin_db, 2),
            "worst_frequency_hz": round(res.worst_frequency_hz, 1),
            "filter_z_out_peak_ohm": round(mb.peak_z_out_ohm, 4),
            "filter_z_out_peak_hz": round(mb.peak_f_hz, 1),
            "converter_z_in_ohm": round(mb.z_in_ohm, 3),
            "middlebrook_separation_db": round(mb.separation_db, 2),
        })
    return rows


def sizing_rows() -> list[dict]:
    return [
        {"quantity": s.quantity, "unit": s.unit,
         "required": f"{s.required:.6g}", "chosen": f"{s.chosen:.6g}",
         "direction": "chosen >= required" if s.higher_is_better else "chosen <= required",
         "margin_pct": round(s.margin_pct, 2) if np.isfinite(s.margin_pct) else "",
         "pass": bool(s.ok), "note": s.note}
        for s in all_sizing()
    ]


def derating_rows() -> list[dict]:
    rows = []
    for v_in in (SYSTEM.vin_min_v, SYSTEM.vin_nom_v, SYSTEM.vin_max_v):
        frac, amb = derating_curve(v_in, 10)
        for f, a in zip(frac, amb):
            rows.append({"v_in_v": v_in, "load_fraction": round(float(f), 3),
                         "max_ambient_c": round(float(a), 2)})
    return rows


def headline() -> dict:
    """The handful of numbers the README quotes."""
    tree_nom = solve_power_tree(SYSTEM.vin_nom_v)
    emc = emc_summary_rows()
    worst_emc = min(emc, key=lambda r: r["worst_margin_db"])
    return {
        "system_efficiency_nom_pct": round(100 * tree_nom.efficiency, 2),
        "total_loss_nom_w": round(tree_nom.total_loss_w, 3),
        "useful_output_w": round(tree_nom.p_useful_w, 3),
        "max_ambient_full_load_c": round(min(max_ambient_c(v)
                                             for v in (SYSTEM.vin_min_v,
                                                       SYSTEM.vin_nom_v,
                                                       SYSTEM.vin_max_v)), 1),
        "worst_emc_margin_db": worst_emc["worst_margin_db"],
        "worst_emc_v_in_v": worst_emc["v_in_v"],
        "worst_middlebrook_separation_db": round(
            min(r["middlebrook_separation_db"] for r in emc), 2),
    }
