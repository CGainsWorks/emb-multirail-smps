"""The design itself: plants, operating points and the compensators chosen.

This is the one module that ties the specification, the chosen components and
the models together. Everything downstream - plots, CSVs, the validation
report, the SPICE netlists and the tests - imports from here, so there is a
single definition of what the board is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import components as C
from .analysis import LoopMargins, log_sweep, margins
from .compensation import (E24, E96, TypeII, TypeIII, design_type_ii,
                           design_type_iii, dominant_pole_hz, resonance_hz, snap)
from .spec import SYSTEM, rail
from .statespace import CurrentModeLoop, boost_model, buck_model
from .switching import SimConfig, type_ii_tf, type_iii_tf

Plant = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class OperatingPoint:
    label: str
    v_in_v: float
    i_out_a: float
    is_design_point: bool = False


@dataclass(frozen=True)
class Divider:
    r_top_ohm: float
    r_bot_ohm: float
    v_ref_v: float

    @property
    def k(self) -> float:
        return self.r_bot_ohm / (self.r_top_ohm + self.r_bot_ohm)

    @property
    def v_out_v(self) -> float:
        return self.v_ref_v / self.k


def make_divider(v_out: float, v_ref: float, r_bot: float) -> Divider:
    r_top = snap(r_bot * (v_out - v_ref) / v_ref, E96)
    return Divider(r_top, r_bot, v_ref)


# --------------------------------------------------------------------------
# +5V rail, synchronous buck, peak current mode
# --------------------------------------------------------------------------

BUCK5_DIVIDER = make_divider(5.0, C.BUCK5["v_ref_v"], 4.99e3)
BUCK5_RI = C.BUCK5["r_sense_ohm"] * C.BUCK5["csa_gain"]


def buck5_ops() -> list[OperatingPoint]:
    return [
        OperatingPoint("Vin 24 V, 5.0 A", SYSTEM.vin_nom_v, 5.0, True),
        OperatingPoint("Vin 8 V, 5.0 A", SYSTEM.vin_min_v, 5.0),
        OperatingPoint("Vin 36 V, 5.0 A", SYSTEM.vin_max_v, 5.0),
        OperatingPoint("Vin 24 V, 0.5 A", SYSTEM.vin_nom_v, 0.5),
        OperatingPoint("Vin 36 V, 0.5 A", SYSTEM.vin_max_v, 0.5),
    ]


def buck5_loop(op: OperatingPoint) -> CurrentModeLoop:
    p = C.BUCK5
    r = rail("+5V")
    r_load = r.v_out_v / max(op.i_out_a, 1e-3)
    model = buck_model(p["L_H"], p["Cout_F"], p["L_dcr_ohm"], p["Cout_esr_ohm"],
                       p["rds_hs_ohm"], p["rds_ls_ohm"], r_load)
    u = np.array([op.v_in_v, 0.0])
    duty = model.duty_for_vout(r.v_out_v, u)
    # Sensed current slopes at this operating point. Se = Sf is chosen because
    # it makes mc*D' = 1 at every duty ratio, so the fsw/2 pole pair keeps the
    # same damping across the whole 8 to 36 V input range. See
    # docs/compensation/buck5v_peak_current_mode.md.
    sn = BUCK5_RI * (op.v_in_v - r.v_out_v) / p["L_H"]
    se = BUCK5_RI * r.v_out_v / p["L_H"]
    return CurrentModeLoop(model, duty, u, r.f_sw_hz, BUCK5_RI, se, sn)


def buck5_plant(op: OperatingPoint) -> Plant:
    loop = buck5_loop(op)
    return lambda f: loop.g_vc(f)


def buck5_compensator() -> TypeII:
    r = rail("+5V")
    p = C.BUCK5
    design_op = [o for o in buck5_ops() if o.is_design_point][0]
    plant = buck5_plant(design_op)
    f_zero = dominant_pole_hz(plant, 10.0, r.f_sw_hz / 2)
    f_pole = r.f_sw_hz / 2.0
    return design_type_ii(plant, r.f_cross_target_hz, f_zero, f_pole,
                          p["gm_ea_s"], p["ea_ro_ohm"], BUCK5_DIVIDER.k)


# --------------------------------------------------------------------------
# +3V3 rail, synchronous buck, voltage mode, Type III
# --------------------------------------------------------------------------

BUCK3V3_R1 = 10.2e3


def buck3v3_ops() -> list[OperatingPoint]:
    v_src = rail("+5V").v_out_v
    return [
        OperatingPoint("Vin 5.0 V, 3.0 A", v_src, 3.0, True),
        OperatingPoint("Vin 4.95 V, 3.0 A", v_src * 0.99, 3.0),
        OperatingPoint("Vin 5.05 V, 3.0 A", v_src * 1.01, 3.0),
        OperatingPoint("Vin 5.0 V, 0.3 A", v_src, 0.3),
    ]


def buck3v3_model(op: OperatingPoint):
    p = C.BUCK3V3
    r = rail("+3V3")
    r_load = r.v_out_v / max(op.i_out_a, 1e-3)
    return buck_model(p["L_H"], p["Cout_F"], p["L_dcr_ohm"], p["Cout_esr_ohm"],
                      p["rds_hs_ohm"], p["rds_ls_ohm"], r_load)


def buck3v3_plant(op: OperatingPoint) -> Plant:
    """Modulator gain times control-to-output. ``Fm = 1/Vramp``."""
    p = C.BUCK3V3
    r = rail("+3V3")
    model = buck3v3_model(op)
    u = np.array([op.v_in_v, 0.0])
    duty = model.duty_for_vout(r.v_out_v, u)
    fm = 1.0 / p["v_ramp_vpp"]
    return lambda f: fm * model.g_vd(f, duty, u)


def buck3v3_compensator() -> TypeIII:
    r = rail("+3V3")
    p = C.BUCK3V3
    design_op = [o for o in buck3v3_ops() if o.is_design_point][0]
    plant = buck3v3_plant(design_op)
    f_lc = resonance_hz(plant, 1e3, 500e3)
    return design_type_iii(
        plant,
        f_cross_hz=r.f_cross_target_hz,
        f_zero_hz=0.5 * f_lc,
        f_pole2_hz=r.f_sw_hz / 2.0,
        f_pole3_hz=r.f_sw_hz,
        v_out=r.v_out_v,
        v_ref=p["v_ref_v"],
        r1_ohm=BUCK3V3_R1,
        a0_db=p["ea_a0_db"],
        gbw_hz=p["ea_gbw_hz"],
    )


# --------------------------------------------------------------------------
# +12V rail, synchronous boost, peak current mode
# --------------------------------------------------------------------------

BOOST12_DIVIDER = make_divider(12.0, C.BOOST12["v_ref_v"], 4.99e3)
BOOST12_RI = C.BOOST12["r_sense_ohm"] * C.BOOST12["csa_gain"]


def boost12_ops() -> list[OperatingPoint]:
    v_src = rail("+5V").v_out_v
    return [
        OperatingPoint("Vin 5.0 V, 0.40 A", v_src, 0.40, True),
        OperatingPoint("Vin 4.95 V, 0.40 A", v_src * 0.99, 0.40),
        OperatingPoint("Vin 5.05 V, 0.40 A", v_src * 1.01, 0.40),
        OperatingPoint("Vin 5.0 V, 0.10 A", v_src, 0.10),
    ]


def boost12_loop(op: OperatingPoint) -> CurrentModeLoop:
    p = C.BOOST12
    r = rail("+12V")
    r_load = r.v_out_v / max(op.i_out_a, 1e-4)
    model = boost_model(p["L_H"], p["Cout_F"], p["L_dcr_ohm"], p["Cout_esr_ohm"],
                        p["rds_lo_ohm"], p["rds_hi_ohm"], r_load)
    u = np.array([op.v_in_v, 0.0])
    duty = model.duty_for_vout(r.v_out_v, u)
    sn = BOOST12_RI * op.v_in_v / p["L_H"]
    se = BOOST12_RI * (r.v_out_v - op.v_in_v) / p["L_H"]
    return CurrentModeLoop(model, duty, u, r.f_sw_hz, BOOST12_RI, se, sn)


def boost12_plant(op: OperatingPoint) -> Plant:
    loop = boost12_loop(op)
    return lambda f: loop.g_vc(f)


def boost12_compensator() -> TypeII:
    r = rail("+12V")
    p = C.BOOST12
    design_op = [o for o in boost12_ops() if o.is_design_point][0]
    plant = boost12_plant(design_op)
    f_zero = dominant_pole_hz(plant, 1.0, r.f_sw_hz / 2)
    f_pole = r.f_sw_hz / 2.0
    return design_type_ii(plant, r.f_cross_target_hz, f_zero, f_pole,
                          p["gm_ea_s"], p["ea_ro_ohm"], BOOST12_DIVIDER.k)


# --------------------------------------------------------------------------
# +1V8A rail, LDO. Behavioural loop model, see components.LDO1V8.
# --------------------------------------------------------------------------

def ldo_r_out_ohm(i_load_a: float) -> float:
    """Small signal output impedance of the pass device at a given load.

    ``gm = 2*Id/Vov`` for the pass FET, inside a local loop of gain
    ``A_local``, so ``r_out = 1/(gm*A_local)``. The preload current is added to
    the external load because that is the point of fitting a preload: it stops
    the output pole walking down to a frequency where the loop cannot cope.
    """
    p = C.LDO1V8
    r = rail("+1V8A")
    i_preload = r.v_out_v / p["preload_r_ohm"]
    i_total = max(i_load_a, 0.0) + i_preload
    gm = 2.0 * i_total / p["pass_vov_v"]
    r_pass = 1.0 / (gm * p["local_loop_gain"])
    r_load = r.v_out_v / max(i_total, 1e-9)
    return 1.0 / (1.0 / r_pass + 1.0 / r_load)


def ldo_loop_gain(i_load_a: float, c_out_f: float | None = None) -> Plant:
    """Loop gain of the LDO.

    This board does not design the LDO loop, it inherits it. The model exists
    to answer the question the designer does control: does the chosen output
    capacitor and preload keep the loop stable across the whole load range.

    The internal gain, dominant pole and parasitic pole are behavioural model
    parameters representing an internally compensated part specified as stable
    with any ceramic output capacitor. They are assumptions. The compensation
    zero tracks the output pole, because that tracking is the mechanism such a
    part must use to make that claim. None of this is measured, and the only
    honest confirmation is a bench Bode plot, which has not been done. This is
    the weakest model in the repository and ``STATUS.md`` says so.
    """
    p = C.LDO1V8
    c_out = p["Cout_F"] if c_out_f is None else c_out_f
    esr = p["Cout_esr_ohm"]

    a0 = 10 ** (p["a0_db"] / 20.0)
    r_out = ldo_r_out_ohm(i_load_a)
    f_out = 1.0 / (2 * np.pi * r_out * c_out)
    f_zero = p["zero_tracking_ratio"] * f_out
    f_esr = 1.0 / (2 * np.pi * esr * c_out)

    def t(f_hz):
        s = 2j * np.pi * np.atleast_1d(np.asarray(f_hz, dtype=float))
        num = (1 + s / (2 * np.pi * f_zero)) * (1 + s / (2 * np.pi * f_esr))
        den = ((1 + s / (2 * np.pi * p["fp1_hz"]))
               * (1 + s / (2 * np.pi * f_out))
               * (1 + s / (2 * np.pi * p["fp_parasitic_hz"])))
        return a0 * num / den

    return t


def ldo_psrr_db(f_hz, i_load_a: float = 0.5) -> np.ndarray:
    """Modelled power supply rejection.

    Two mechanisms in series. Inside the loop bandwidth the loop rejects input
    ripple by ``1 + T``. Outside it the only thing left is the passive divider
    made by the pass device output impedance and the output capacitor.
    """
    p = C.LDO1V8
    f_hz = np.atleast_1d(np.asarray(f_hz, dtype=float))
    t = ldo_loop_gain(i_load_a)(f_hz)
    r_out = ldo_r_out_ohm(i_load_a)
    c_out = p["Cout_F"]
    z_c = 1.0 / (2j * np.pi * f_hz * c_out) + p["Cout_esr_ohm"]
    passive = np.abs(z_c / (r_out + z_c))
    feedthrough = 10 ** (p["feedthrough_db"] / 20.0)
    return -20.0 * np.log10(feedthrough * passive / np.abs(1.0 + t))


def ldo_input_filter_db(f_hz) -> np.ndarray:
    """Attenuation of the series RC filter feeding the LDO input.

    ``R`` in series into the existing input capacitor. First order, no
    peaking, and the price is ``R * Iin`` of headroom and ``R * Iin^2`` of
    heat. See components.LDO1V8 for why an LC was not used.
    """
    p = C.LDO1V8
    f = np.atleast_1d(np.asarray(f_hz, dtype=float))
    s = 2j * np.pi * f
    h = 1.0 / (1.0 + s * p["input_rc_r_ohm"] * p["Cin_F"])
    return -20.0 * np.log10(np.abs(h))


def ldo_total_rejection_db(f_hz, i_load_a: float = 0.5) -> np.ndarray:
    """Input filter plus LDO supply rejection, which is what the rail sees."""
    return ldo_input_filter_db(f_hz) + ldo_psrr_db(f_hz, i_load_a)


# --------------------------------------------------------------------------
# Assembled results
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class LoopResult:
    rail: str
    op: str
    is_design_point: bool
    f: np.ndarray
    t: np.ndarray
    margins: LoopMargins


def sweep_for(rail_name: str) -> np.ndarray:
    if rail_name == "+12V":
        return log_sweep(1.0, 200e3, 80)
    if rail_name == "+1V8A":
        return log_sweep(1.0, 10e6, 80)
    if rail_name == "+3V3":
        return log_sweep(10.0, 5e6, 80)
    return log_sweep(10.0, 1e6, 80)


def all_loops() -> list[LoopResult]:
    """Loop gain at every operating point for every rail."""
    out: list[LoopResult] = []

    comp5 = buck5_compensator()
    f5 = sweep_for("+5V")
    for op in buck5_ops():
        t = comp5.response(f5) * buck5_plant(op)(f5)
        out.append(LoopResult("+5V", op.label, op.is_design_point, f5, t, margins(f5, t)))

    comp3 = buck3v3_compensator()
    f3 = sweep_for("+3V3")
    for op in buck3v3_ops():
        t = comp3.response(f3) * buck3v3_plant(op)(f3)
        out.append(LoopResult("+3V3", op.label, op.is_design_point, f3, t, margins(f3, t)))

    comp12 = boost12_compensator()
    f12 = sweep_for("+12V")
    for op in boost12_ops():
        t = comp12.response(f12) * boost12_plant(op)(f12)
        out.append(LoopResult("+12V", op.label, op.is_design_point, f12, t, margins(f12, t)))

    fl = sweep_for("+1V8A")
    for i_load, label, design in ((0.5, "Iload 0.50 A", True),
                                  (0.05, "Iload 0.05 A", False),
                                  (0.0, "Iload 0 A, preload only", False)):
        t = ldo_loop_gain(i_load)(fl)
        out.append(LoopResult("+1V8A", label, design, fl, t, margins(fl, t)))

    return out


def compensator_summary() -> list[dict]:
    """Chosen compensation values, for docs and for the BOM."""
    rows: list[dict] = []
    c5 = buck5_compensator()
    rows.append({"rail": "+5V", "network": "Type II, gm error amp",
                 "Rc_ohm": c5.rc_ohm, "Cc_F": c5.cc_f, "Cp_F": c5.cp_f,
                 "f_zero_Hz": round(c5.f_zero_hz, 1), "f_pole_Hz": round(c5.f_pole_hz, 1),
                 "Rtop_ohm": BUCK5_DIVIDER.r_top_ohm, "Rbot_ohm": BUCK5_DIVIDER.r_bot_ohm})
    c3 = buck3v3_compensator()
    rows.append({"rail": "+3V3", "network": "Type III, voltage feedback error amp",
                 "R1_ohm": c3.r1_ohm, "Rbot_ohm": c3.rbot_ohm, "R3_ohm": c3.r3_ohm,
                 "Rf_ohm": c3.rf_ohm, "Cf1_F": c3.cf1_f, "Cf2_F": c3.cf2_f,
                 "Cf3_F": c3.cf3_f,
                 "f_zero1_Hz": round(c3.f_zero1_hz, 1), "f_zero2_Hz": round(c3.f_zero2_hz, 1),
                 "f_pole2_Hz": round(c3.f_pole2_hz, 1), "f_pole3_Hz": round(c3.f_pole3_hz, 1)})
    c12 = boost12_compensator()
    rows.append({"rail": "+12V", "network": "Type II, gm error amp",
                 "Rc_ohm": c12.rc_ohm, "Cc_F": c12.cc_f, "Cp_F": c12.cp_f,
                 "f_zero_Hz": round(c12.f_zero_hz, 1), "f_pole_Hz": round(c12.f_pole_hz, 1),
                 "Rtop_ohm": BOOST12_DIVIDER.r_top_ohm, "Rbot_ohm": BOOST12_DIVIDER.r_bot_ohm})
    return rows


# --------------------------------------------------------------------------
# Bridge to the switching simulator
# --------------------------------------------------------------------------

def sim_config(rail_name: str, op: OperatingPoint) -> SimConfig:
    """Build a cycle accurate simulation of one rail at one operating point.

    The compensator handed to the simulator is the same object the analytic
    loop gain uses, so a disagreement between the two can only come from the
    power stage model or from the modulator, which is the point of the check.
    """
    if rail_name == "+5V":
        p = C.BUCK5
        r = rail("+5V")
        loop = buck5_loop(op)
        comp = buck5_compensator()
        num, den = type_ii_tf(comp.rc_ohm, comp.cc_f, comp.cp_f,
                              comp.gm_s, comp.ro_ohm, comp.k_div)
        v_target = BUCK5_DIVIDER.v_out_v
        di = r.v_out_v * (1 - loop.duty) / (p["L_H"] * r.f_sw_hz)
        i_pk = op.i_out_a + di / 2
        t_on = loop.duty / r.f_sw_hz
        return SimConfig(
            model=loop.model, comp_num=num, comp_den=den, f_sw=r.f_sw_hz,
            v_in=op.v_in_v, v_target=v_target, mode="peak-current",
            ri=loop.ri, se_v_per_s=loop.se,
            il_init=op.i_out_a, vc_init=v_target,
            vcomp_init=loop.ri * i_pk + loop.se * t_on,
        )

    if rail_name == "+3V3":
        p = C.BUCK3V3
        r = rail("+3V3")
        comp = buck3v3_compensator()
        num, den = type_iii_tf(comp.r1_ohm, comp.r3_ohm, comp.rf_ohm,
                               comp.cf1_f, comp.cf2_f, comp.cf3_f)
        v_target = p["v_ref_v"] * (comp.r1_ohm + comp.rbot_ohm) / comp.rbot_ohm
        model = buck3v3_model(op)
        u = np.array([op.v_in_v, 0.0])
        duty = model.duty_for_vout(v_target, u)
        return SimConfig(
            model=model, comp_num=num, comp_den=den, f_sw=r.f_sw_hz,
            v_in=op.v_in_v, v_target=v_target, mode="voltage",
            v_ramp_low=0.0, v_ramp_pp=p["v_ramp_vpp"],
            il_init=op.i_out_a, vc_init=v_target, vcomp_init=duty,
        )

    if rail_name == "+12V":
        p = C.BOOST12
        r = rail("+12V")
        loop = boost12_loop(op)
        comp = boost12_compensator()
        num, den = type_ii_tf(comp.rc_ohm, comp.cc_f, comp.cp_f,
                              comp.gm_s, comp.ro_ohm, comp.k_div)
        v_target = BOOST12_DIVIDER.v_out_v
        i_l = op.i_out_a / (1 - loop.duty)
        di = op.v_in_v * loop.duty / (p["L_H"] * r.f_sw_hz)
        t_on = loop.duty / r.f_sw_hz
        return SimConfig(
            model=loop.model, comp_num=num, comp_den=den, f_sw=r.f_sw_hz,
            v_in=op.v_in_v, v_target=v_target, mode="peak-current",
            ri=loop.ri, se_v_per_s=loop.se,
            il_init=i_l, vc_init=v_target,
            vcomp_init=loop.ri * (i_l + di / 2) + loop.se * t_on,
        )

    raise KeyError(f"no switching model for rail {rail_name!r}")


def analytic_loop(rail_name: str, op: OperatingPoint):
    """The analytic loop gain for the same rail and operating point."""
    if rail_name == "+5V":
        comp = buck5_compensator()
        plant = buck5_plant(op)
    elif rail_name == "+3V3":
        comp = buck3v3_compensator()
        plant = buck3v3_plant(op)
    elif rail_name == "+12V":
        comp = boost12_compensator()
        plant = boost12_plant(op)
    else:
        raise KeyError(rail_name)
    return lambda f: comp.response(f) * plant(f)


def design_point(rail_name: str) -> OperatingPoint:
    ops = {"+5V": buck5_ops, "+3V3": buck3v3_ops, "+12V": boost12_ops}[rail_name]()
    return [o for o in ops if o.is_design_point][0]
