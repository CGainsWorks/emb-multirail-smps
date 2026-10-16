"""Selected components and the parasitics used by every model in this repo.

IMPORTANT - read before quoting any of this
-------------------------------------------
The numeric values here are *modelling assumptions*, chosen to be typical of
the described part class, except where a comment says a figure was read from
the selected part's data sheet. Real parts have now been selected for every
line (see ``smps.hardware``) and ``outputs/VERIFY.csv`` says, line by line,
where the data sheet and the model still disagree. No part has been bought,
measured or reflowed.
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
    # Current sense: 5 mOhm shunt. The selected controller (LTC3891) senses
    # it directly; the x10 gain stands for its internal current comparator
    # and is a modelling assumption, not a datasheet figure.
    "r_sense_ohm": 5e-3,
    "csa_gain": 10.0,
    # Error amplifier, from the LTC3891 datasheet (Rev C) electrical
    # characteristics: VFB 0.800 V, gm 2 mmho typical. The output resistance
    # is not specified there and stays an assumption.
    "v_ref_v": 0.8,
    "gm_ea_s": 2.0e-3,
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
    # Reference, ramp and error amplifier, from the TPS54317 datasheet
    # (SLVS619B) electrical characteristics: Vref 0.891 V, ramp 1 Vpp,
    # open loop gain 110 dB typical, unity gain bandwidth 5 MHz typical.
    # The FET and switching figures above are still the earlier assumptions;
    # see outputs/VERIFY.csv for how they compare with that datasheet.
    "v_ref_v": 0.891,
    "v_ramp_vpp": 1.0,
    "ea_gbw_hz": 5e6,
    "ea_a0_db": 110.0,
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
    # Current sense: 50 mOhm shunt in series with the inductor. The selected
    # controller (TPS43061) senses it directly; the x3 gain stands for its
    # internal current comparator and is a modelling assumption.
    "r_sense_ohm": 50e-3,
    "csa_gain": 3.0,
    # Error amplifier, from the TPS43061 datasheet (SLVSBP4D) electrical
    # characteristics: VREF 1.22 V, Gea 1.1 mS, Rea 10 MOhm, all typical.
    "v_ref_v": 1.22,
    "gm_ea_s": 1.1e-3,
    "ea_ro_ohm": 10e6,
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
    Part("U1", "Synchronous buck controller, peak current mode, 4 to 60 V",
         "-", "TSSOP-20 exposed pad", 1, "Analog Devices LTC3891EFE#PBF",
         "Read from the data sheet and now used by the model: VFB 0.800 V, "
         "gm 2 mmho typical. Still an assumption: the effective current sense "
         "gain (modelled as a x10 amplifier on the 5 mOhm shunt), slope "
         "compensation, error amplifier output resistance. Gate drive is "
         "INTVCC, about 5.1 V from EXTVCC, where the loss model assumes 7.5 V. "
         "ILIM is set to 50 mV, which with 5 mOhm limits at 8.6 to 11.4 A, "
         "above the 9 A modelled inductor saturation",
         {"gm_ea_s": BUCK5["gm_ea_s"], "v_ref_v": BUCK5["v_ref_v"]}),
    Part("Q1,Q2", "N-channel MOSFET, 60 V, NexFET SON 3.3 x 3.3",
         "60V", "SON-3x3", 2, "TI CSD18543Q3A",
         "Data sheet: 8.1 / 9.9 mOhm typ / max at Vgs 10 V and 12.0 / 15.6 "
         "mOhm at 4.5 V, Qg 5.6 nC at 4.5 V. The model uses 11 mOhm and 12 nC "
         "at 7.5 V but the gate is driven at about 5.1 V. Rds(on) at 5 V and "
         "100 C, Qoss and the pinout drawing still to be read",
         {"rds_ohm": BUCK5["rds_hs_ohm"]}),
    Part("L1", "Shielded power inductor, 6.8 uH",
         "6.8uH", "XAL8080", 1, "Coilcraft XAL8080-682MED",
         "Data sheet: DCR 13.2 / 14.5 mOhm typ / max, Isat 14.0 A at 30 % "
         "drop. The model uses 11 mOhm and 9 A. No 6 x 6 mm part meets both "
         "figures, so the footprint grew to 8 x 8 mm. Core loss coefficients "
         "are still an assumption",
         {"L_H": BUCK5["L_H"]}),
    Part("Rs1", "Current sense shunt, 5 mOhm, 1 %, 1 W, 4 terminal",
         "5m", "2512-4T", 1, "Vishay WSK25125L000FEA",
         "Data sheet: 1 W at 70 C, 1 %, TCR 35 ppm/C. Power rating with the "
         "actual copper pour still to be checked",
         {"r_ohm": BUCK5["r_sense_ohm"]}),
    Part("C1,C2", "MLCC 10 uF 50 V X7R 1210", "10uF/50V", "1210", 2,
         "Murata GRM32ER71H106KA12L",
         "DC bias derating at 24 V and 36 V; the 0.45 factor used here is an "
         "assumption", {}),
    Part("C3", "Hybrid polymer aluminium 220 uF 50 V", "220uF/50V", "10 x 16.5 mm",
         1, "Panasonic EEH-ZS1H221P",
         "Listing: ESR 13 mOhm max at 100 kHz, 3.7 A ripple. The model uses "
         "15 mOhm and this part damps the input filter, so the lower ESR moves "
         "the Middlebrook margin the wrong way: re-run the input filter study "
         "with the data sheet ESR before ordering. No 10 x 10 mm 220 uF 50 V "
         "hybrid was found", {}),
    Part("L4", "Differential mode input inductor, 10 uH", "10uH", "XAL7050", 1,
         "Coilcraft XAL7050-103MEC",
         "Data sheet: DCR 25 / 29 mOhm, Isat 7.1 A. The input filter model "
         "uses 40 mOhm, which is part of its damping, so this too moves the "
         "Middlebrook margin and has to be re-run", {}),
    Part("C12", "MLCC 2.2 uF 100 V X7R 1210, input filter", "2.2uF/100V", "1210",
         1, "Murata GRM32ER72A225KA35L",
         "The model treats this as 2.2 uF with no DC bias derating, as a film "
         "part would be. No film part of this value was found in a small SMD "
         "case, so it is an MLCC and its derating at 24 to 36 V has to be "
         "read from the Murata curves and added to the EMC model", {}),
    Part("C4-C6", "MLCC 22 uF 25 V X7R 1210", "22uF/25V", "1210", 3,
         "Murata GRM32ER71E226KE15L",
         "DC bias derating at 5 V; the 0.70 factor used here is an assumption. "
         "Some distributors list the part as not for new designs", {}),
    Part("Rc1,Cc1,Cp1", "Type II compensation network, +5V rail", "see docs", "0402", 3, "-",
         "Design choice, not a part property. Values from smps.compensation", {}),

    Part("U3", "Synchronous buck regulator, voltage mode, 3 to 6 V in, 3 A, "
               "integrated FETs", "-", "QFN-24 4 x 5 mm", 1,
         "TI TPS54317RHFR",
         "Read from the data sheet and now used by the model: Vref 0.891 V, "
         "ramp 1 Vpp, error amplifier 110 dB and 5 MHz. Data sheet FET "
         "resistance is 59 mOhm typical at 6 V in, where the loss model still "
         "uses 30 and 20 mOhm, so the +3V3 efficiency and U3 temperature are "
         "optimistic until it is re-run. The data sheet dates from 2009: "
         "confirm the part is still recommended for new designs and the RHF "
         "land pattern against TI's drawing", {}),
    Part("L2", "Shielded power inductor, 1.5 uH", "1.5uH", "XGL4020", 1,
         "Coilcraft XGL4020-152MEC",
         "Data sheet: DCR 13.0 / 14.3 mOhm, Isat 5.3 A at 20 % and 7.5 A at "
         "30 % drop. The model uses 15 mOhm and 6 A. Core loss at 1 MHz still "
         "an assumption", {}),
    Part("C7,C8", "MLCC 22 uF 16 V X7R 1206", "22uF/16V", "1206", 2,
         "Murata GRM31CZ71C226ME15L",
         "DC bias derating at 3.3 V; the 0.75 factor used here is an assumption",
         {}),
    Part("R1,R3,Rf2,Cf1,Cf2,Cf3", "Type III compensation network, +3V3 rail",
         "see docs", "0402", 6, "-",
         "Design choice, not a part property. Values from smps.compensation", {}),

    Part("U4", "Synchronous boost controller, peak current mode", "-",
         "WQFN-16 3 x 3 mm", 1, "TI TPS43061RTER",
         "Read from the data sheet and now used by the model: VREF 1.22 V, "
         "Gea 1.1 mS, Rea 10 MOhm. Still an assumption: the effective current "
         "sense gain (modelled as x3 on the 50 mOhm shunt) and slope "
         "compensation. The current limit, 61 to 73 mV over 50 mOhm, is 1.2 to "
         "1.5 A against a 1.13 A modelled peak: thin", {}),
    Part("Q3,Q4", "N-channel MOSFET, 30 V, SOT-23", "30V", "SOT-23", 2,
         "Alpha and Omega AO3400A",
         "Data sheet: 19 / 32 mOhm typ / max at Vgs 4.5 V, Qg 6 nC. The model "
         "uses 40 mOhm and 2.5 nC at 5 V; the gate charge is more than double", {}),
    Part("L3", "Shielded power inductor, 22 uH", "22uH", "XGL6060", 1,
         "Coilcraft XGL6060-223MEC",
         "Data sheet: DCR 42.6 / 46.9 mOhm, Isat 2.5 A at 10 % and 3.9 A at "
         "20 % drop. The model uses 45 mOhm and 2.5 A. Core loss at 400 kHz "
         "still an assumption", {}),
    Part("C9,C10", "MLCC 22 uF 25 V X7R 1210", "22uF/25V", "1210", 2,
         "Murata GRM32ER71E226KE15L",
         "DC bias derating at 12 V; the 0.55 factor used here is an assumption", {}),

    Part("U5", "Low noise LDO, fixed 1.8 V, 0.5 A", "-", "WSON-6 2 x 2 mm", 1,
         "TI LP5912-1.8DRVR",
         "The LDO loop model is behavioural and was not refitted to this part. "
         "Stability over Cout and load, PSRR at 500 kHz and dropout at 0.5 A "
         "to be read from the data sheet", {}),
    Part("C11", "MLCC 10 uF 6.3 V X7R 0805", "10uF/6.3V", "0805", 1,
         "Murata GRM21BR70J106KE76L", "DC bias derating at 1.8 V", {}),
    Part("Rf1", "LDO input filter resistor, 0.33 ohm 1 %, 0.25 W", "0R33", "0805", 1,
         "Yageo RL0805FR-7W0R33L",
         "Design choice. 86 mW at 0.51 A against a 0.25 W rating", {}),
    Part("C13", "MLCC 10 uF 16 V X7R 0805, LDO input filter capacitor",
         "10uF/16V", "0805", 1, "Samsung CL21B106KOQNNNE", "DC bias derating at 3.3 V", {}),
    Part("Rpl1", "Preload resistor, 180 ohm, holds 10 mA minimum LDO load", "180R",
         "0603", 1, "Yageo RC0603FR-07180RL",
         "Design choice. Confirm the LP5912 actually needs a preload", {}),

    Part("D1", "TVS, 36 V stand off, SOD-123FL", "SMF36A", "SOD-123FL", 1,
         "Littelfuse SMF36A",
         "Stand off equals the 36 V maximum input and breakdown starts at "
         "40 V, so there is no margin at the top of the input range", {}),
    Part("F1", "Fuse, 3 A slow blow, 63 V DC, 1206", "3A", "1206", 1,
         "Eaton Bussmann CC12H3A-TR",
         "DC rating from distributor listings; the Eaton data sheet was not "
         "reached. Check I2t against the input capacitor inrush", {}),
    Part("J1", "Input terminal block, 2 way, 5.08 mm", "-", "MKDS 3/2-5.08", 1,
         "Phoenix Contact 1711725", "Current rating, creepage", {}),
    Part("J2", "Output terminal block, 10 way, 5.08 mm", "-", "MKDS 1,5/10-5.08", 1,
         "Phoenix Contact 1715802", "Current rating", {}),
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
    """The model's view of the parts: what was selected for each modelled
    role and what is still an assumption. The fitted BOM, one line per part
    number, is :func:`smps.hardware.bom_rows`."""
    return [
        {
            "ref": p.ref,
            "qty": p.qty,
            "description": p.description,
            "value": p.value,
            "package": p.package,
            "candidate_mpn": p.candidate_mpn,
            "mpn_status": ("design value" if p.candidate_mpn == "-"
                           else "selected, data sheet check pending"),
        }
        for p in BOM
    ]
