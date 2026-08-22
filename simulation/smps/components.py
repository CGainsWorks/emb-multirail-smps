"""Selected components and the parasitics used by every model in this repo.

IMPORTANT - read before quoting any of this
-------------------------------------------
The numeric values here are *modelling assumptions*, chosen to be typical of
the described part class. They have not been read back out of a live datasheet
by any automated process, and no part has been bought, measured or reflowed.
Every entry therefore carries ``verify`` text naming what has to be checked
against the manufacturer's current datasheet before a board is ordered. The
generated file ``outputs/VERIFY.csv`` collects them into one checklist.

Where a value is a *design choice* rather than a claimed part property, the
``verify`` field says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Part:
    """One BOM line, plus whatever parasitics the models need."""

    ref: str
    description: str
    value: str
    package: str
    qty: int
    candidate_mpn: str
    verify: str
    #: Model parameters consumed by smps.* modules. Units are in the key name.
    params: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Ceramic capacitor DC bias derating
# --------------------------------------------------------------------------
# X7R MLCCs lose a large fraction of their nameplate capacitance under DC bias.
# Ignoring this is the single most common reason a bench ripple measurement
# comes in two or three times worse than the simulation. The factors below are
# the derating actually applied throughout this repository.

CERAMIC_DERATING = {
    # (nominal_uF, rated_V, applied_V): retained fraction
    ("22uF", "25V", 5.0): 0.70,
    ("22uF", "16V", 3.3): 0.75,
    ("22uF", "25V", 12.0): 0.55,
    ("10uF", "50V", 24.0): 0.45,
    ("10uF", "16V", 5.0): 0.70,
    ("10uF", "6.3V", 1.8): 0.70,
}


# --------------------------------------------------------------------------
# Rail +5V: synchronous buck, peak current mode, VIN 8-36 V, 5 A
# --------------------------------------------------------------------------

BUCK5 = {
    "L_H": 6.8e-6,
    "L_dcr_ohm": 11e-3,
    "L_isat_a": 9.0,
    "Cout_F": 3 * 22e-6 * CERAMIC_DERATING[("22uF", "25V", 5.0)],
    "Cout_esr_ohm": 2e-3 / 3,
    "Cin_F": 2 * 10e-6 * CERAMIC_DERATING[("10uF", "50V", 24.0)],
    "Cin_esr_ohm": 3e-3 / 2,
    # Sized by the input filter study in smps.emc: big enough to damp the
    # differential mode inductor so the Middlebrook criterion still holds.
    "Cbulk_F": 220e-6,
    "Cbulk_esr_ohm": 15e-3,
    "rds_hs_ohm": 11e-3,
    "rds_ls_ohm": 11e-3,
    "qg_hs_c": 12e-9,
    "qg_ls_c": 12e-9,
    "qoss_hs_c": 8e-9,
    "vgs_drive_v": 7.5,
    "t_rise_s": 12e-9,
    "t_fall_s": 12e-9,
    "t_dead_s": 30e-9,
    "vf_body_v": 0.85,
    # Current sense: 5 mOhm shunt into a x10 current-sense amplifier.
    "r_sense_ohm": 5e-3,
    "csa_gain": 10.0,
    "v_ref_v": 0.8,
    "gm_ea_s": 1.2e-3,
    "ea_ro_ohm": 20e6,
    # Core loss, Steinmetz form Pv = k f^alpha B^beta in W/m^3 with f in Hz
    # and B in T. These coefficients are an assumption fitted to give roughly
    # 90 kW/m^3 at 500 kHz and 45 mT, which is typical of a moulded composite
    # power inductor. They are not from the part datasheet and are the single
    # least trustworthy number in this file. See outputs/VERIFY.csv.
    "core_k": 0.19,
    "core_alpha": 1.55,
    "core_beta": 2.35,
    "core_ve_m3": 1.2e-7,
    "core_ae_m2": 1.6e-5,
    "core_n_turns": 6.0,
}

# --------------------------------------------------------------------------
# Rail +3V3: synchronous buck, voltage mode, from +5V, 3 A
# --------------------------------------------------------------------------

BUCK3V3 = {
    "L_H": 1.5e-6,
    "L_dcr_ohm": 15e-3,
    "L_isat_a": 6.0,
    "Cout_F": 2 * 22e-6 * CERAMIC_DERATING[("22uF", "16V", 3.3)],
    "Cout_esr_ohm": 2e-3 / 2,
    "Cin_F": 2 * 10e-6 * CERAMIC_DERATING[("10uF", "16V", 5.0)],
    "Cin_esr_ohm": 3e-3 / 2,
    "rds_hs_ohm": 30e-3,
    "rds_ls_ohm": 20e-3,
    "qg_hs_c": 3e-9,
    "qg_ls_c": 4e-9,
    "qoss_hs_c": 1.5e-9,
    "vgs_drive_v": 5.0,
    "t_rise_s": 5e-9,
    "t_fall_s": 5e-9,
    "t_dead_s": 12e-9,
    "vf_body_v": 0.8,
    "v_ref_v": 0.8,
    "v_ramp_vpp": 1.0,
    "ea_gbw_hz": 12e6,
    "ea_a0_db": 80.0,
    "core_k": 0.15,
    "core_alpha": 1.6,
    "core_beta": 2.3,
    "core_ve_m3": 4.0e-8,
    "core_ae_m2": 8.0e-6,
    "core_n_turns": 4.0,
}

# --------------------------------------------------------------------------
# Rail +12V: synchronous boost, peak current mode, from +5V, 0.4 A
# --------------------------------------------------------------------------

BOOST12 = {
    "L_H": 22e-6,
    "L_dcr_ohm": 45e-3,
    "L_isat_a": 2.5,
    "Cout_F": 2 * 22e-6 * CERAMIC_DERATING[("22uF", "25V", 12.0)],
    "Cout_esr_ohm": 3e-3 / 2,
    "Cin_F": 10e-6 * CERAMIC_DERATING[("10uF", "16V", 5.0)],
    "Cin_esr_ohm": 3e-3,
    "rds_lo_ohm": 40e-3,
    "rds_hi_ohm": 40e-3,
    "qg_lo_c": 2.5e-9,
    "qg_hi_c": 2.5e-9,
    "qoss_hi_c": 1.2e-9,
    "vgs_drive_v": 5.0,
    "t_rise_s": 8e-9,
    "t_fall_s": 8e-9,
    "t_dead_s": 15e-9,
    "vf_body_v": 0.8,
    # Current sense: 50 mOhm shunt into a x3 current-sense amplifier.
    "r_sense_ohm": 50e-3,
    "csa_gain": 3.0,
    "v_ref_v": 0.8,
    "gm_ea_s": 0.6e-3,
    "ea_ro_ohm": 20e6,
    "core_k": 0.18,
    "core_alpha": 1.58,
    "core_beta": 2.3,
    "core_ve_m3": 1.0e-7,
    "core_ae_m2": 1.0e-5,
    "core_n_turns": 18.0,
}

# --------------------------------------------------------------------------
# Rail +1V8A: low noise LDO from +3V3, 0.5 A
# --------------------------------------------------------------------------
# Behavioural model of an internally compensated PMOS LDO. The internal pole,
# zero and gain are model parameters chosen to reproduce a datasheet-typical
# stability envelope; they are not measured and not read from a datasheet.

LDO1V8 = {
    "Cout_F": 10e-6 * CERAMIC_DERATING[("10uF", "6.3V", 1.8)],
    "Cout_esr_ohm": 3e-3,
    "Cin_F": 10e-6 * CERAMIC_DERATING[("10uF", "16V", 5.0)],
    "v_ref_v": 0.8,
    # Loop: internal dominant pole, an output pole set by the pass device
    # small signal output impedance and Cout, an internal compensation zero
    # that tracks the output pole (which is what a part specified as "stable
    # with any ceramic output capacitor" has to do), and one parasitic pole.
    "a0_db": 60.0,
    "fp1_hz": 200.0,
    "fp_parasitic_hz": 400e3,
    "zero_tracking_ratio": 0.5,
    # Pass device transconductance, gm = 2*Id/Vov, inside a local loop of gain
    # A_local, so the small signal output impedance is 1/(gm*A_local).
    "pass_vov_v": 0.35,
    "local_loop_gain": 20.0,
    "iq_a": 55e-6,
    "dropout_v_at_imax": 0.25,
    "preload_r_ohm": 180.0,
    # Series RC filter on the LDO input. The LDO's own supply rejection runs
    # out well below the 3V3 buck's 1 MHz switching frequency, so on its own it
    # does not meet the analogue rail's ripple budget against the worst case
    # 3V3 ripple. A resistor into the existing input capacitor fixes that for
    # the cost of 0.33 * Iin volts of headroom and about 90 mW. An LC would
    # cost less power but needs damping, and an undamped LC in front of an LDO
    # is a peaking filter, not a filter.
    "input_rc_r_ohm": 0.33,
    # Open loop supply feedthrough before the loop and the output capacitor
    # act on it. Together with the loop gain this sets the modelled PSRR.
    "feedthrough_db": -6.0,
    "noise_uvrms_10hz_100khz": 12.0,
}


# --------------------------------------------------------------------------
# BOM
# --------------------------------------------------------------------------

BOM: tuple[Part, ...] = (
    Part("U1", "Synchronous buck controller, peak current mode, external compensation, 6-75 V",
         "-", "HTSSOP-20", 1, "TI LM5145 (candidate)",
         "Vin range, COMP pin gm, internal ramp/slope-comp behaviour, SS timing",
         {"gm_ea_s": BUCK5["gm_ea_s"], "v_ref_v": BUCK5["v_ref_v"]}),
    Part("Q1,Q2", "N-channel MOSFET, 60 V, 11 mOhm, PowerPAK/SON 3.3x3.3",
         "60V 11m", "SON-3x3", 2, "TI CSD18543Q3A (candidate)",
         "Rds(on) at Vgs=7.5 V and 100 C, Qg, Qoss, thermal pad Rth",
         {"rds_ohm": BUCK5["rds_hs_ohm"]}),
    Part("L1", "Shielded power inductor, 6.8 uH, 9 A saturation, 11 mOhm DCR",
         "6.8uH", "XAL60xx", 1, "Coilcraft XAL6060-682 (candidate)",
         "Isat at 125 C, DCR at 100 C, core loss coefficients",
         {"L_H": BUCK5["L_H"]}),
    Part("Rs1", "Current sense shunt, 5 mOhm, 1 %, 2 W, 4 terminal",
         "5m", "2512-4T", 1, "Vishay WSL2512 (candidate)",
         "Tolerance, TCR, power rating with the actual copper pour",
         {"r_ohm": BUCK5["r_sense_ohm"]}),
    Part("U2", "Current sense amplifier, gain 10", "x10", "SOT-23-5", 1,
         "TI INA declared TBD (candidate)",
         "Bandwidth must exceed 5x fsw, input CM range covers the switch node side",
         {"gain": BUCK5["csa_gain"]}),
    Part("C1,C2", "MLCC 10 uF 50 V X7R", "10uF/50V", "1210", 2, "TBD",
         "DC bias derating at 24 V and 36 V - the 0.45 factor used here is an assumption", {}),
    Part("C3", "Aluminium polymer 220 uF 50 V, 15 mOhm ESR", "220uF/50V", "SMD 10x10", 1, "TBD",
         "ESR over temperature and its spread, ripple current rating. This part "
         "damps the input filter, so a low ESR substitute is not a safe swap", {}),
    Part("L4", "Differential mode input inductor, 10 uH, 3 A, 40 mOhm",
         "10uH", "SMD 7x7", 1, "TBD",
         "Saturation current at 3 A, self resonant frequency above 30 MHz", {}),
    Part("C12", "Film capacitor 2.2 uF 63 V X2 style", "2.2uF/63V", "SMD", 1, "TBD",
         "Self resonance, ESL. Placed at the connector, not next to the FETs", {}),
    Part("C4-C6", "MLCC 22 uF 25 V X7R", "22uF/25V", "1210", 3, "TBD",
         "DC bias derating at 5 V - the 0.70 factor used here is an assumption", {}),
    Part("Rc1,Cc1,Cp1", "Type II compensation network, +5V rail", "see docs", "0402", 3, "-",
         "Design choice, not a part property. Values from smps.compensation", {}),

    Part("U3", "Synchronous buck regulator, voltage mode, 6 V in, 3 A, integrated FETs",
         "-", "VQFN-16", 1, "TBD",
         "Ramp amplitude Vramp, error amp GBW, Rds(on) of both FETs", {}),
    Part("L2", "Shielded power inductor, 1.5 uH, 6 A saturation, 15 mOhm DCR",
         "1.5uH", "XAL40xx", 1, "Coilcraft XAL4020-152 (candidate)",
         "Isat, DCR, core loss at 1 MHz", {}),
    Part("C7,C8", "MLCC 22 uF 16 V X7R", "22uF/16V", "1206", 2, "TBD",
         "DC bias derating at 3.3 V - the 0.75 factor used here is an assumption", {}),
    Part("R1,R3,Rf,Cf1,Cf2,Cf3", "Type III compensation network, +3V3 rail",
         "see docs", "0402", 6, "-",
         "Design choice, not a part property. Values from smps.compensation", {}),

    Part("U4", "Synchronous boost controller, peak current mode", "-", "VSSOP-10", 1, "TBD",
         "Minimum on time, maximum duty clamp, slope compensation", {}),
    Part("Q3,Q4", "N-channel MOSFET, 30 V, 40 mOhm", "30V 40m", "SOT-23", 2, "TBD",
         "Rds(on) at Vgs=5 V, Qg, Qoss", {}),
    Part("L3", "Shielded power inductor, 22 uH, 2.5 A saturation, 45 mOhm DCR",
         "22uH", "XAL50xx", 1, "TBD", "Isat, DCR, core loss at 400 kHz", {}),
    Part("C9,C10", "MLCC 22 uF 25 V X7R", "22uF/25V", "1210", 2, "TBD",
         "DC bias derating at 12 V - the 0.55 factor used here is an assumption", {}),

    Part("U5", "Low noise LDO, 1.8 V fixed or adjustable, 0.5 A", "-", "WSON-6", 1, "TBD",
         "Stability envelope over Cout and load, PSRR at 500 kHz, dropout at 0.5 A", {}),
    Part("C11", "MLCC 10 uF 6.3 V X7R", "10uF/6.3V", "0805", 1, "TBD",
         "DC bias derating at 1.8 V", {}),
    Part("Rf1", "LDO input filter resistor, 0.33 ohm 1 %, 1 W", "0R33", "0805", 1, "-",
         "Design choice. Power rating at 0.51 A, and the headroom it costs", {}),
    Part("C13", "MLCC 10 uF 16 V X7R, LDO input filter capacitor",
         "10uF/16V", "0805", 1, "TBD", "DC bias derating at 3.3 V", {}),
    Part("Rpl", "Preload resistor, 180 ohm, holds 10 mA minimum LDO load", "180R", "0603", 1, "-",
         "Design choice. Confirm the chosen LDO actually needs a preload", {}),

    Part("FB1", "Common mode choke, 2 x 100 uH, 2 A", "2x100uH", "SMD", 1, "TBD",
         "Leakage inductance, saturation current, self resonance", {}),
    Part("J1", "Input connector, 40 V, 2 A", "-", "-", 1, "TBD", "Current rating, creepage", {}),
    Part("J2", "Output connector, 4 rails plus returns", "-", "-", 1, "TBD", "Current rating", {}),
)


def verify_rows() -> list[dict]:
    """Rows for ``outputs/VERIFY.csv``."""
    return [
        {
            "ref": p.ref,
            "description": p.description,
            "candidate_mpn": p.candidate_mpn,
            "must_verify_before_ordering": p.verify,
        }
        for p in BOM
    ]


def bom_rows() -> list[dict]:
    return [
        {
            "ref": p.ref,
            "qty": p.qty,
            "description": p.description,
            "value": p.value,
            "package": p.package,
            "candidate_mpn": p.candidate_mpn,
            "mpn_status": "candidate, unverified" if p.candidate_mpn not in ("-", "TBD")
            else ("design value" if p.candidate_mpn == "-" else "not selected"),
        }
        for p in BOM
    ]
