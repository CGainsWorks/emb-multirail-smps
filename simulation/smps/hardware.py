"""The board: every part, its value, part number, footprint and connections.

This is the data the KiCad schematic in ``hardware/kicad/`` was generated from
(``scripts/kicad/gen_schematic.py``) and the data the checks hold it to
(``scripts/kicad/check_netlist.py``). Every value that the simulation also
uses is read from :mod:`smps.design` or :mod:`smps.components` here rather
than typed in, so the schematic cannot quietly carry a different compensation
network from the one the loop analysis was run on.

Three kinds of value appear and the ``basis`` field of each part says which:

``model``
    Used by the simulation. Sizing, compensation and the input filter.
``datasheet``
    Support parts around a controller (timing resistors, bootstrap,
    soft-start, bias capacitors), sized from the controller's data sheet. The
    equation or table used is given. None of these is simulated.
``choice``
    A design decision with no equation behind it, such as a pull-up value.

Part numbers are real and were checked to exist; see ``outputs/VERIFY.csv``
for what still has to be confirmed against each data sheet before ordering.
Nothing here has been bought, fitted or measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from . import components as C
from . import design as D

PROJECT = "emb-multirail-smps"

#: (file stem, title shown on the sheet)
SHEETS = (
    ("input_5v", "Input protection, input filter and +5V buck"),
    ("buck_3v3", "+3V3 voltage mode buck"),
    ("boost_12v", "+12V synchronous boost"),
    ("ldo_outputs", "+1V8A low noise LDO and output connector"),
)


@dataclass(frozen=True)
class Part:
    ref: str
    sheet: str
    symbol: str
    value: str
    footprint: str
    manufacturer: str
    mpn: str
    #: pin number -> net name. ``None`` marks a pin deliberately left open.
    pins: dict
    description: str
    basis: str = "model"
    #: SI value for resistors, capacitors and inductors, ``None`` otherwise.
    nominal: float | None = None
    note: str = ""


@dataclass(frozen=True)
class Controller:
    """What the set point and loop checks need to know about each IC."""

    ref: str
    rail: str
    v_ref_v: float
    source: str
    divider_top: tuple = field(default_factory=tuple)
    divider_bottom: str = ""


# --------------------------------------------------------------------------
# Value formatting and part number catalogues
# --------------------------------------------------------------------------

_PREFIX = ((1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "u"),
           (1e-9, "n"), (1e-12, "p"))


def eng(x: float, unit: str = "") -> str:
    """``26100 -> 26.1k``, ``1.5e-8, "F" -> 15nF``. Three significant figures."""
    if x == 0:
        return "0" + unit
    for scale, prefix in _PREFIX:
        if abs(x) >= scale * 0.9995:
            v = x / scale
            text = f"{v:.3g}"
            return f"{text}{prefix}{unit}"
    return f"{x:.3g}{unit}"


def _yageo_code(ohms: float) -> str:
    """Yageo RC series resistance field: 26.1k -> 26K1, 115 -> 115R, 1M -> 1M."""
    for scale, letter in ((1e6, "M"), (1e3, "K"), (1.0, "R")):
        if ohms >= scale:
            v = f"{ohms / scale:.3g}"
            whole, _, frac = v.partition(".")
            return f"{whole}{letter}{frac}"
    raise ValueError(ohms)


def yageo(ohms: float, size: str) -> str:
    """Yageo RC series thick film, 1 %, 7 inch reel, lead free."""
    if ohms == 0:
        return f"RC{size}JR-070RL"
    return f"RC{size}FR-07{_yageo_code(ohms)}L"


R_FOOTPRINT = {
    "0402": "Resistor_SMD:R_0402_1005Metric",
    "0603": "Resistor_SMD:R_0603_1608Metric",
    "0805": "Resistor_SMD:R_0805_2012Metric",
}
C_FOOTPRINT = {
    "0402": "Capacitor_SMD:C_0402_1005Metric",
    "0603": "Capacitor_SMD:C_0603_1608Metric",
    "0805": "Capacitor_SMD:C_0805_2012Metric",
    "1206": "Capacitor_SMD:C_1206_3216Metric",
    "1210": "Capacitor_SMD:C_1210_3225Metric",
}

#: (value F, size) -> (manufacturer, MPN, rating). Ceramic capacitors whose
#: part numbers were confirmed on the manufacturer's or a distributor's site.
CAPACITORS = {
    (10e-6, "1210"): ("Murata", "GRM32ER71H106KA12L", "50V X7R"),
    (22e-6, "1210"): ("Murata", "GRM32ER71E226KE15L", "25V X7R"),
    (22e-6, "1206"): ("Murata", "GRM31CZ71C226ME15L", "16V X7R"),
    (10e-6, "0805"): ("Samsung", "CL21B106KOQNNNE", "16V X7R"),
    (4.7e-6, "0805"): ("Murata", "GRM21BR71C475KA73L", "16V X7R"),
    (1e-6, "0603"): ("Murata", "GRM188R71C105KA12D", "16V X7R"),
    (100e-9, "0402"): ("Murata", "GRM155R71H104KE14D", "50V X7R"),
    (100e-9, "0603"): ("Murata", "GRM188R71H104KA93D", "50V X7R"),
    (47e-9, "0402"): ("Murata", "GRM155R71C473KA01D", "16V X7R"),
    (22e-9, "0402"): ("Murata", "GRM155R71H223KA12D", "50V X7R"),
    (15e-9, "0402"): ("Murata", "GRM155R71H153KA12D", "50V X7R"),
    (3.3e-9, "0402"): ("Murata", "GRM1555C1H332JE01D", "50V C0G"),
    (1.3e-9, "0402"): ("KEMET", "C0402C132J5GACTU", "50V C0G"),
    (270e-12, "0402"): ("KEMET", "C0402C271J5GACTU", "50V C0G"),
    (75e-12, "0402"): ("KEMET", "C0402C750J5GACTU", "50V C0G"),
    # Input filter shunt. No film part of this value exists in a small SMD
    # case, so it is an X7R MLCC rated well above the input; see VERIFY.csv
    # for the DC bias derating the input filter model does not yet include.
    (2.2e-6, "1210-100V"): ("Murata", "GRM32ER72A225KA35L", "100V X7R"),
}

#: The 10 uF 6.3 V on the LDO output is X7R in 0805 like the others.
CAPACITORS[(10e-6, "0805-6V3")] = ("Murata", "GRM21BR70J106KE76L", "6.3V X7R")


def cap_part(value: float, size: str) -> tuple[str, str, str]:
    key = (value, size)
    for (v, s), entry in CAPACITORS.items():
        if s == size and abs(v - value) <= 1e-3 * value:
            return entry
    raise KeyError(f"no confirmed part number for {eng(value, 'F')} {size}")


# --------------------------------------------------------------------------
# Part constructors
# --------------------------------------------------------------------------

def R(ref, sheet, ohms, a, b, size="0402", basis="model", desc="", note="",
      part=None):
    maker, mpn = part or ("Yageo", yageo(ohms, size))
    return Part(ref, sheet, "Device:R", eng(ohms), R_FOOTPRINT[size], maker,
                mpn, {"1": a, "2": b},
                desc or f"Resistor {eng(ohms)} 1 % {size}", basis, ohms, note)


def Cap(ref, sheet, farads, a, b, size="0402", basis="model", desc="", note="",
        catalogue_size=None):
    maker, mpn, rating = cap_part(farads, catalogue_size or size)
    return Part(ref, sheet, "Device:C", eng(farads, "F"), C_FOOTPRINT[size],
                maker, mpn, {"1": a, "2": b},
                desc or f"MLCC {eng(farads, 'F')} {rating} {size}", basis,
                farads, note)


def _r(x: float) -> float:
    """Undo binary noise on a value read from the design, to 4 figures."""
    return float(f"{x:.4g}")


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def board() -> tuple[Part, ...]:
    c5 = D.buck5_compensator()
    c3 = D.buck3v3_compensator()
    c12 = D.boost12_compensator()
    d5 = D.BUCK5_DIVIDER
    d12 = D.BOOST12_DIVIDER
    ldo = C.LDO1V8

    S1, S2, S3, S4 = (s for s, _ in SHEETS)
    parts: list[Part] = []
    add = parts.append

    # ---------------------------------------------------------------- input
    add(Part("J1", S1, "Connector:Screw_Terminal_01x02", "VIN 8-36V",
             "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal",
             "Phoenix Contact", "1711725", {"1": "VIN_CONN", "2": "GND"},
             "Input terminal block, 2 way, 5.08 mm", "choice"))
    add(Part("F1", S1, "Device:Fuse", "3A", "Fuse:Fuse_1206_3216Metric",
             "Eaton Bussmann", "CC12H3A-TR", {"1": "VIN_CONN", "2": "VIN_F"},
             "Fuse, 3 A slow blow, 63 V DC, 1206", "choice"))
    add(Part("D1", S1, "Device:D_Zener", "SMF36A", "Diode_SMD:D_SOD-123F",
             "Littelfuse", "SMF36A", {"1": "VIN_F", "2": "GND"},
             "TVS, 36 V stand off, unidirectional, SOD-123FL. Clamps input "
             "transients and conducts on reverse polarity until F1 opens",
             "choice"))
    add(Cap("C12", S1, 2.2e-6, "VIN_F", "GND", size="1210",
            desc="Input filter shunt capacitor, connector side, 2.2 uF 100 V X7R",
            catalogue_size="1210-100V"))
    add(Part("L4", S1, "Device:L", "10uH",
             "Inductor_SMD:L_Coilcraft_XAL7050-XXX", "Coilcraft", "XAL7050-103MEC",
             {"1": "VIN_F", "2": "VIN"},
             "Differential mode input filter inductor, 10 uH", "model", 10e-6))
    add(Part("C3", S1, "Device:C_Polarized", "220uF", "Capacitor_SMD:CP_Elec_10x10.5",
             "Panasonic", "EEH-ZS1H221P", {"1": "VIN", "2": "GND"},
             "Hybrid polymer aluminium 220 uF 50 V, 10 x 16.5 mm, input filter "
             "damping", "model", 220e-6,
             note="Land pattern is set by the 10 mm can diameter; the can is "
                  "16.5 mm tall, so confirm the pad layout against Panasonic's "
                  "drawing."))
    for ref in ("C1", "C2"):
        add(Cap(ref, S1, 10e-6, "VIN", "GND", size="1210",
                desc="+5V buck input capacitor, 10 uF 50 V X7R 1210"))

    # ---------------------------------------------------------------- +5V buck
    add(Part("U1", S1, "smps:LTC3891xFE", "LTC3891EFE#PBF",
             "Package_SO:HTSSOP-20-1EP_4.4x6.5mm_P0.65mm_EP2.74x3.86mm",
             "Analog Devices", "LTC3891EFE#PBF",
             {"1": "INTVCC_5V", "2": "GND", "3": "GND", "4": "RUN_5V",
              "5": "CS_5V_N", "6": "CS_5V_P", "7": "FB_5V", "8": "COMP_5V",
              "9": "PG_5V", "10": "HG_5V", "11": "SW_5V", "12": "BST_5V",
              "13": "LG_5V", "14": "INTVCC_5V", "15": "+5V", "16": "GND",
              "17": "VIN", "18": "INTVCC_5V", "19": "SS_5V", "20": "FREQ_5V",
              "21": "GND"},
             "60 V synchronous buck controller, peak current mode, 0.8 V "
             "reference", "datasheet",
             note="PLLIN/MODE to INTVCC selects forced continuous conduction, "
                  "which is what the model assumes. ILIM to INTVCC sets a 50 mV "
                  "current limit. EXTVCC from +5V."))
    for ref, net_d, net_s, net_g, role in (("Q1", "VIN", "SW_5V", "HG_5V", "high side"),
                                           ("Q2", "SW_5V", "GND", "LG_5V", "low side")):
        add(Part(ref, S1, "Transistor_FET:CSD18543Q3A", "CSD18543Q3A",
                 "Package_SON:VSON-8_3.3x3.3mm_P0.65mm_NexFET",
                 "Texas Instruments", "CSD18543Q3A",
                 {"1": net_s, "2": net_s, "3": net_s, "4": net_g, "5": net_d},
                 f"60 V N-channel MOSFET, {role}", "choice"))
    add(Part("D2", S1, "Device:D_Schottky", "PMEG6010CEH", "Diode_SMD:D_SOD-123F",
             "Nexperia", "PMEG6010CEH", {"1": "BST_5V", "2": "INTVCC_5V"},
             "Bootstrap diode, 60 V Schottky. The data sheet calls for one "
             "between INTVCC and BOOST", "datasheet"))
    add(Cap("C14", S1, 100e-9, "BST_5V", "SW_5V", size="0603", basis="datasheet",
            desc="Bootstrap capacitor, 0.1 uF 50 V"))
    add(Cap("C15", S1, 4.7e-6, "INTVCC_5V", "GND", size="0805", basis="datasheet",
            desc="INTVCC decoupling. Data sheet minimum 2.2 uF"))
    add(Cap("C16", S1, 100e-9, "VIN", "GND", basis="datasheet",
            desc="VIN pin bypass to SGND"))
    add(Cap("C17", S1, 47e-9, "SS_5V", "GND", basis="datasheet",
            desc="Soft start. tSS = CSS * 0.8 V / 10 uA = 3.8 ms"))
    add(R("R10", S1, 71.5e3, "FREQ_5V", "GND", basis="datasheet",
          desc="Frequency set, 500 kHz",
          note="Linear interpolation between the data sheet's characterised "
               "points (65k gives 440 kHz, 105k gives 835 kHz). Confirm "
               "against its frequency curve."))
    add(R("R11", S1, 1e6, "VIN", "RUN_5V", size="0603", basis="datasheet",
          desc="RUN divider top. Starts at about 7 V rising"))
    add(R("R12", S1, 210e3, "RUN_5V", "GND", basis="datasheet",
          desc="RUN divider bottom. 1.21 V threshold, 6.3 V at 36 V in"))
    add(R("R13", S1, 100e3, "PG_5V", "+5V", basis="choice", desc="PGOOD pull-up"))
    add(Part("L1", S1, "Device:L", "6.8uH", "Inductor_SMD:L_Coilcraft_XAL8080-XXX",
             "Coilcraft", "XAL8080-682MED", {"1": "SW_5V", "2": "SNS_5V"},
             "+5V buck inductor, 6.8 uH", "model", C.BUCK5["L_H"]))
    add(Part("Rs1", S1, "Device:R_Shunt", "5m",
             "Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm",
             "Vishay", "WSK25125L000FEA",
             {"1": "SNS_5V", "2": "CS_5V_P", "3": "CS_5V_N", "4": "+5V"},
             "Current sense shunt, 5 mOhm 1 %, four terminal 2512", "model",
             C.BUCK5["r_sense_ohm"]))
    for ref in ("C4", "C5", "C6"):
        add(Cap(ref, S1, 22e-6, "+5V", "GND", size="1210",
                desc="+5V output capacitor, 22 uF 25 V X7R 1210"))
    add(R("R14", S1, 0.0, "+5V", "FBTOP_5V", size="0603", basis="choice",
          desc="Loop injection link. Fitted 0 ohm; replace with 20 ohm for a "
               "Bode measurement"))
    add(R("Rt1", S1, _r(d5.r_top_ohm), "FBTOP_5V", "FB_5V", desc="+5V divider top"))
    add(R("Rb1", S1, _r(d5.r_bot_ohm), "FB_5V", "GND", desc="+5V divider bottom"))
    add(R("Rc1", S1, _r(c5.rc_ohm), "COMP_5V", "COMPZ_5V",
          desc="+5V Type II, Rc"))
    add(Cap("Cc1", S1, _r(c5.cc_f), "COMPZ_5V", "GND", desc="+5V Type II, Cc"))
    add(Cap("Cp1", S1, _r(c5.cp_f), "COMP_5V", "GND", desc="+5V Type II, Cp"))

    # ---------------------------------------------------------------- +3V3 buck
    add(Part("U3", S2, "smps:TPS54317xRHF", "TPS54317RHFR",
             "Package_DFN_QFN:QFN-24-1EP_4x5mm_P0.5mm_EP2.65x3.65mm",
             "Texas Instruments", "TPS54317RHFR",
             {"1": "COMP_3V3", "2": "PG_3V3", "3": "BST_3V3",
              **{str(n): "SW_3V3" for n in range(4, 10)}, "10": None,
              **{str(n): "GND" for n in range(11, 15)},
              **{str(n): "+5V" for n in range(15, 18)}, "18": "VBIAS_3V3",
              "19": "SS_3V3", "20": None, "21": None, "22": "RT_3V3",
              "23": "GND", "24": "FB_3V3", "25": "GND"},
             "3 to 6 V input, 3 A synchronous buck, voltage mode, integrated "
             "FETs, 0.891 V reference", "datasheet",
             note="SYNC left open with RT fitted sets the frequency from RT."))
    for ref in ("C18", "C19"):
        add(Cap(ref, S2, 10e-6, "+5V", "GND", size="0805",
                desc="+3V3 buck input capacitor, 10 uF 16 V X7R 0805"))
    add(Cap("C20", S2, 47e-9, "BST_3V3", "SW_3V3", basis="datasheet",
            desc="Bootstrap capacitor. Data sheet range 0.022 to 0.1 uF"))
    add(Cap("C21", S2, 100e-9, "VBIAS_3V3", "GND", basis="datasheet",
            desc="VBIAS decoupling. Data sheet range 0.1 to 1 uF"))
    add(Cap("C22", S2, 22e-9, "SS_3V3", "GND", basis="datasheet",
            desc="Slow start. t = C * 0.7 V / 5 uA = 3.1 ms"))
    add(R("R20", S2, 46.4e3, "RT_3V3", "GND", basis="datasheet",
          desc="Frequency set, 1 MHz. f(MHz) = 51k / (R + 4.7k) gives 46.3k"))
    add(R("R21", S2, 100e3, "PG_3V3", "+3V3", basis="choice", desc="PWRGD pull-up"))
    add(Part("L2", S2, "Device:L", "1.5uH", "Inductor_SMD:L_Coilcraft_XAL4020-XXX",
             "Coilcraft", "XGL4020-152MEC", {"1": "SW_3V3", "2": "+3V3"},
             "+3V3 buck inductor, 1.5 uH", "model", C.BUCK3V3["L_H"],
             note="XGL4020 shares the 4 x 4 mm body of the XAL4020 whose land "
                  "pattern is used; confirm against the XGL4020 drawing."))
    for ref in ("C7", "C8"):
        add(Cap(ref, S2, 22e-6, "+3V3", "GND", size="1206",
                desc="+3V3 output capacitor, 22 uF 16 V X7R 1206"))
    add(R("R22", S2, 0.0, "+3V3", "FBTOP_3V3", size="0603", basis="choice",
          desc="Loop injection link. Fitted 0 ohm; replace with 20 ohm for a "
               "Bode measurement"))
    add(R("R1", S2, _r(c3.r1_ohm), "FBTOP_3V3", "FB_3V3",
          desc="+3V3 Type III R1, also the divider top"))
    add(R("Rb2", S2, _r(c3.rbot_ohm), "FB_3V3", "GND", desc="+3V3 divider bottom"))
    add(R("R3", S2, _r(c3.r3_ohm), "FBTOP_3V3", "N3_3V3", desc="+3V3 Type III R3"))
    add(Cap("Cf3", S2, _r(c3.cf3_f), "N3_3V3", "FB_3V3", desc="+3V3 Type III Cf3"))
    add(R("Rf2", S2, _r(c3.rf_ohm), "COMP_3V3", "NF_3V3", desc="+3V3 Type III Rf"))
    add(Cap("Cf1", S2, _r(c3.cf1_f), "NF_3V3", "FB_3V3", desc="+3V3 Type III Cf1"))
    add(Cap("Cf2", S2, _r(c3.cf2_f), "COMP_3V3", "FB_3V3", desc="+3V3 Type III Cf2"))

    # ---------------------------------------------------------------- +12V boost
    add(Part("U4", S3, "Converter_DCDC:TPS43060RTE", "TPS43061RTER",
             "Package_DFN_QFN:Texas_RTE_WQFN-16-1EP_3x3mm_P0.5mm_EP1.2x0.8mm",
             "Texas Instruments", "TPS43061RTER",
             {"1": "RT_12V", "2": "SS_12V", "3": "COMP_12V", "4": "FB_12V",
              "5": "SNS_12V", "6": "+5V", "7": "+5V", "8": "LDRV_12V", "9": "GND",
              "10": "VCC_12V", "11": "BST_12V", "12": "SW_12V", "13": "HDRV_12V",
              "14": "PG_12V", "15": None, "16": "GND", "17": "GND"},
             "Synchronous boost controller, peak current mode, 5.5 V gate "
             "drive, integrated bootstrap diode, 1.22 V reference", "datasheet",
             note="TPS43061 shares the TPS43060 pinout and symbol. EN is left "
                  "open, which the data sheet says enables the part through its "
                  "internal pull-up."))
    add(R("R33", S3, 0.0, "HDRV_12V", "HG_12V", basis="choice",
          desc="High side gate resistor. Fitted 0 ohm, there to slow the "
               "edge if the switch node rings on the real board"))
    add(R("R34", S3, 0.0, "LDRV_12V", "LG_12V", basis="choice",
          desc="Low side gate resistor. Fitted 0 ohm, as R33"))
    add(Cap("C23", S3, 10e-6, "+5V", "GND", size="0805",
            desc="+12V boost input capacitor, 10 uF 16 V X7R 0805"))
    add(Cap("C24", S3, 100e-9, "+5V", "GND", basis="datasheet",
            desc="VIN pin bypass. Data sheet asks for 0.1 uF or more"))
    add(Cap("C25", S3, 1e-6, "VCC_12V", "GND", size="0603", basis="datasheet",
            desc="VCC decoupling. Data sheet range 0.47 to 10 uF"))
    add(Cap("C26", S3, 100e-9, "BST_12V", "SW_12V", size="0603", basis="datasheet",
            desc="Bootstrap capacitor, 0.1 uF as in the data sheet example"))
    add(Cap("C27", S3, 47e-9, "SS_12V", "GND", basis="datasheet",
            desc="Soft start. t = C * 1.22 V / 5 uA = 11 ms"))
    add(R("R30", S3, 147e3, "RT_12V", "GND", basis="datasheet",
          desc="Frequency set, 400 kHz",
          note="Power law fit through the data sheet's characterised points "
               "(115k gives 500 kHz, 75k gives 750 kHz). Confirm against "
               "its Equation 14."))
    add(R("R31", S3, 10e3, "PG_12V", "VCC_12V", basis="datasheet",
          desc="PGOOD pull-up to VCC, 10k as the data sheet recommends"))
    add(R("Rs2", S3, C.BOOST12["r_sense_ohm"], "+5V", "SNS_12V", size="0805",
          desc="Current sense shunt, 50 mOhm 1 %, in series with the inductor",
          part=("Vishay", "WSLP0805R0500FEA")))
    add(Part("L3", S3, "Device:L", "22uH", "Inductor_SMD:L_Coilcraft_XAL6060-XXX",
             "Coilcraft", "XGL6060-223MEC", {"1": "SNS_12V", "2": "SW_12V"},
             "+12V boost inductor, 22 uH", "model", C.BOOST12["L_H"],
             note="XGL6060 shares the 6 x 6 mm body of the XAL6060 whose land "
                  "pattern is used; confirm against the XGL6060 drawing."))
    add(Part("Q3", S3, "Transistor_FET:AO3400A", "AO3400A",
             "Package_TO_SOT_SMD:SOT-23", "Alpha and Omega", "AO3400A",
             {"1": "LG_12V", "2": "GND", "3": "SW_12V"},
             "30 V N-channel MOSFET, boost low side", "choice"))
    add(Part("Q4", S3, "Transistor_FET:AO3400A", "AO3400A",
             "Package_TO_SOT_SMD:SOT-23", "Alpha and Omega", "AO3400A",
             {"1": "HG_12V", "2": "SW_12V", "3": "+12V"},
             "30 V N-channel MOSFET, boost synchronous rectifier", "choice"))
    for ref in ("C9", "C10"):
        add(Cap(ref, S3, 22e-6, "+12V", "GND", size="1210",
                desc="+12V output capacitor, 22 uF 25 V X7R 1210"))
    add(R("R32", S3, 0.0, "+12V", "FBTOP_12V", size="0603", basis="choice",
          desc="Loop injection link. Fitted 0 ohm; replace with 20 ohm for a "
               "Bode measurement"))
    add(R("Rt2", S3, _r(d12.r_top_ohm), "FBTOP_12V", "FB_12V", desc="+12V divider top"))
    add(R("Rb3", S3, _r(d12.r_bot_ohm), "FB_12V", "GND", desc="+12V divider bottom"))
    add(R("Rc2", S3, _r(c12.rc_ohm), "COMP_12V", "COMPZ_12V", desc="+12V Type II, Rc"))
    add(Cap("Cc2", S3, _r(c12.cc_f), "COMPZ_12V", "GND", desc="+12V Type II, Cc"))
    add(Cap("Cp2", S3, _r(c12.cp_f), "COMP_12V", "GND", desc="+12V Type II, Cp"))

    # ---------------------------------------------------------------- LDO
    add(R("Rf1", S4, ldo["input_rc_r_ohm"], "+3V3", "LDO_IN", size="0805",
          desc="LDO input filter resistor, 0.33 ohm 1 %",
          part=("Yageo", "RL0805FR-7W0R33L")))
    add(Cap("C13", S4, 10e-6, "LDO_IN", "GND", size="0805",
            desc="LDO input filter capacitor, 10 uF 16 V X7R 0805"))
    add(Part("U5", S4, "Regulator_Linear:LP5912-1.8DRV", "LP5912-1.8DRVR",
             "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
             "Texas Instruments", "LP5912-1.8DRVR",
             {"1": "+1V8A", "2": None, "3": "PG_1V8A", "4": "LDO_IN",
              "5": "GND", "6": "LDO_IN", "7": "GND"},
             "500 mA low noise LDO, fixed 1.8 V", "datasheet",
             note="EN tied to IN, so the regulator follows its input."))
    add(Cap("C11", S4, 10e-6, "+1V8A", "GND", size="0805",
            desc="LDO output capacitor, 10 uF 6.3 V X7R 0805",
            catalogue_size="0805-6V3"))
    add(R("Rpl1", S4, ldo["preload_r_ohm"], "+1V8A", "GND", size="0603",
          desc="Preload, holds 10 mA minimum load"))
    add(R("R40", S4, 100e3, "PG_1V8A", "+1V8A", basis="choice", desc="PG pull-up"))
    add(Part("J2", S4, "Connector:Screw_Terminal_01x10", "OUTPUTS",
             "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-10-5.08_1x10_P5.08mm_Horizontal",
             "Phoenix Contact", "1715802",
             {"1": "+5V", "2": "GND", "3": "+3V3", "4": "GND", "5": "+12V",
              "6": "GND", "7": "+1V8A", "8": "GND", "9": "GND", "10": "GND"},
             "Output terminal block, 10 way, 5.08 mm", "choice"))
    return tuple(parts)


def controllers() -> tuple[Controller, ...]:
    """The set point of each regulated rail, from the selected parts."""
    return (
        Controller("U1", "+5V", 0.800, "LTC3891 data sheet, VFB typical",
                   ("Rt1",), "Rb1"),
        Controller("U3", "+3V3", 0.891, "TPS54317 data sheet, Vref typical",
                   ("R1",), "Rb2"),
        Controller("U4", "+12V", 1.22, "TPS43061 data sheet, VREF typical",
                   ("Rt2",), "Rb3"),
    )


def by_ref() -> dict[str, Part]:
    return {p.ref: p for p in board()}


def nets() -> dict[str, list[str]]:
    """Net name -> sorted list of ``REF-pin``. Open pins are left out."""
    out: dict[str, list[str]] = {}
    for p in board():
        for pin, net in p.pins.items():
            if net is not None:
                out.setdefault(net, []).append(f"{p.ref}-{pin}")
    return {n: sorted(v) for n, v in sorted(out.items())}


def bom_rows() -> list[dict]:
    """The fitted bill of materials, one line per part number."""
    groups: dict[tuple, list[Part]] = {}
    for p in board():
        groups.setdefault((p.manufacturer, p.mpn), []).append(p)
    rows = []
    for (maker, mpn), ps in groups.items():
        rows.append({
            "refs": " ".join(p.ref for p in ps),
            "qty": len(ps),
            "value": ps[0].value,
            "description": ps[0].description,
            "footprint": ps[0].footprint,
            "manufacturer": maker,
            "mpn": mpn,
            "basis": ps[0].basis,
            "status": "selected, data sheet check pending",
        })
    return rows
