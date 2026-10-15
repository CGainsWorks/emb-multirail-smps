"""Netlist and SPICE deck generation.

Three outputs, and it matters which is which.

``outputs/netlists/ngspice/`` and ``outputs/netlists/ltspice/``
    SPICE decks, in two dialects that are genuinely not interchangeable. The
    ngspice ones are executed by CI on every push and their results compared
    against the Python models; the LTspice ones have never been run. See
    :mod:`smps.spice`.

``outputs/netlists/board.net``
    A Protel format netlist, which is what Altium imports. It is the connection
    list for the schematic, not a layout. Importing it gives a designer the
    correct nets and footprints to place and route against.

``outputs/bom.csv`` and ``outputs/VERIFY.csv``
    The bill of materials, and the list of every number in this repository that
    is an assumption rather than a datasheet value.
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import components as C
from . import design as D
from .spice import ltspice_decks, ngspice_decks


def _fmt(x: float) -> str:
    """SPICE friendly engineering notation."""
    return f"{x:.6g}"


# --------------------------------------------------------------------------
# Protel netlist for Altium
# --------------------------------------------------------------------------

# MOSFET pin convention used throughout this netlist: 1 = drain, 2 = source,
# 3 = gate. Real footprints number their pins differently, and the mapping is
# part of choosing the footprint, not part of the connection list.

#: (designator, footprint, comment)
SCH_PARTS = [
    ("J1", "TB-2P-5MM", "VIN 8-36V"),
    ("F1", "FUSE-1206", "3A"),
    ("D1", "SOD-123", "40V reverse protection"),
    ("L4", "IND-7X7", "10uH differential mode"),
    ("C12", "FILM-1812", "2u2 63V"),
    ("C3", "SMD-10X10", "220uF 50V polymer"),
    ("C1", "1210", "10uF 50V"),
    ("C2", "1210", "10uF 50V"),
    ("U1", "HTSSOP-20-EP", "Sync buck controller, peak current mode"),
    ("Q1", "SON-3X3", "60V 11m NFET, high side"),
    ("Q2", "SON-3X3", "60V 11m NFET, low side"),
    ("Rs1", "2512-4T", "5m 1% shunt"),
    ("U2", "SOT-23-5", "Current sense amp x10"),
    ("L1", "XAL6060", "6u8"),
    ("C4", "1210", "22uF 25V"),
    ("C5", "1210", "22uF 25V"),
    ("C6", "1210", "22uF 25V"),
    ("Rc1", "0402", "Rc, Type II"),
    ("Cc1", "0402", "Cc, Type II"),
    ("Cp1", "0402", "Cp, Type II"),
    ("Rt1", "0402", "Rtop 5V divider"),
    ("Rb1", "0402", "Rbot 5V divider"),
    ("U3", "VQFN-16-EP", "3V3 buck, voltage mode, integrated FETs"),
    ("L2", "XAL4020", "1u5"),
    ("C7", "1206", "22uF 16V"),
    ("C8", "1206", "22uF 16V"),
    ("R1", "0402", "R1, Type III and 3V3 divider top"),
    ("R3", "0402", "R3, Type III"),
    ("Rf", "0402", "Rf, Type III"),
    ("Cf1", "0402", "Cf1, Type III"),
    ("Cf2", "0402", "Cf2, Type III"),
    ("Cf3", "0402", "Cf3, Type III"),
    ("Rb2", "0402", "Rbot 3V3 divider"),
    ("U4", "VSSOP-10", "Sync boost controller, peak current mode"),
    ("Q3", "SOT-23", "30V 40m NFET, low side"),
    ("Q4", "SOT-23", "30V 40m NFET, synchronous rectifier"),
    ("L3", "XAL5030", "22u"),
    ("Rs2", "0805", "50m 1% shunt"),
    ("C9", "1210", "22uF 25V"),
    ("C10", "1210", "22uF 25V"),
    ("Rc2", "0402", "Rc, Type II"),
    ("Cc2", "0402", "Cc, Type II"),
    ("Cp2", "0402", "Cp, Type II"),
    ("Rt2", "0402", "Rtop 12V divider"),
    ("Rb3", "0402", "Rbot 12V divider"),
    ("Rf1", "0805", "0R33 LDO input filter"),
    ("C13", "0805", "10uF 16V LDO input filter"),
    ("U5", "WSON-6-EP", "1V8 LDO 0.5A"),
    ("C11", "0805", "10uF 6V3"),
    ("Rpl", "0603", "180R preload"),
    ("J2", "TB-10P-5MM", "Outputs"),
]

#: net name -> list of "Designator-pin"
SCH_NETS = {
    "VIN_CONN": ["J1-1", "F1-1"],
    "VIN_F": ["F1-2", "D1-1", "C12-1", "L4-1"],
    "VIN": ["L4-2", "C3-1", "C1-1", "C2-1", "U1-1", "Q1-1", "U2-1"],
    "SW5": ["Q1-2", "Q2-1", "U1-8", "L1-1"],
    "SNS5A": ["L1-2", "Rs1-1", "U2-2"],
    "PLUS5": ["Rs1-2", "U2-3", "C4-1", "C5-1", "C6-1", "Rt1-1", "J2-1",
              "U3-1", "U4-1", "L3-1"],
    "CSOUT5": ["U2-4", "U1-6"],
    "FB5": ["Rt1-2", "Rb1-1", "U1-4"],
    "COMP5": ["U1-5", "Rc1-1", "Cp1-1"],
    "COMPZ5": ["Rc1-2", "Cc1-1"],
    "HG5": ["U1-9", "Q1-3"],
    "LG5": ["U1-7", "Q2-3"],

    "SW3V3": ["U3-5", "L2-1"],
    "PLUS3V3": ["L2-2", "C7-1", "C8-1", "R1-1", "R3-1", "J2-3", "Rf1-1"],
    "FB3V3": ["R1-2", "Rb2-1", "Cf1-2", "Cf2-2", "Cf3-2", "U3-8"],
    "N3": ["R3-2", "Cf3-1"],
    "NF": ["Rf-2", "Cf1-1"],
    "COMP3V3": ["U3-9", "Rf-1", "Cf2-1"],

    "SWBOOST": ["L3-2", "Q3-1", "Q4-2", "U4-5"],
    "SNS12": ["Q3-2", "Rs2-1", "U4-7"],
    "LGB": ["U4-8", "Q3-3"],
    "HGB": ["U4-9", "Q4-3"],
    "PLUS12": ["Q4-1", "C9-1", "C10-1", "Rt2-1", "J2-5"],
    "FB12": ["Rt2-2", "Rb3-1", "U4-4"],
    "COMP12": ["U4-6", "Rc2-1", "Cp2-1"],
    "COMPZ12": ["Rc2-2", "Cc2-1"],

    "LDO_IN": ["Rf1-2", "C13-1", "U5-1"],
    "PLUS1V8": ["U5-5", "C11-1", "Rpl-1", "J2-7"],

    "GND": ["J1-2", "D1-2", "C12-2", "C3-2", "C1-2", "C2-2", "U1-2", "Q2-2",
            "U2-5", "C4-2", "C5-2", "C6-2", "Rb1-2", "Cc1-2", "Cp1-2",
            "U3-2", "C7-2", "C8-2", "Rb2-2", "U4-2", "Rs2-2", "C9-2", "C10-2",
            "Rb3-2", "Cc2-2", "Cp2-2", "C13-2", "U5-2", "C11-2", "Rpl-2",
            "J2-2", "J2-4", "J2-6", "J2-8", "J2-9", "J2-10"],
}


def protel_netlist() -> str:
    lines: list[str] = []
    for des, fp, comment in SCH_PARTS:
        lines += ["[", des, fp, comment, "", "", "", "]"]
    for net, pins in SCH_NETS.items():
        lines += ["(", net, *pins, ")"]
    return "\n".join(lines) + "\n"


def netlist_stats() -> dict:
    pins = [p for pins in SCH_NETS.values() for p in pins]
    return {
        "parts": len(SCH_PARTS),
        "nets": len(SCH_NETS),
        "pin_connections": len(pins),
        "single_pin_nets": sum(1 for pins in SCH_NETS.values() if len(pins) < 2),
        "duplicate_pin_connections": len(pins) - len(set(pins)),
        "parts_with_no_net": len([d for d, _, _ in SCH_PARTS
                                  if not any(p.startswith(d + "-") for p in pins)]),
    }


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_all(out_dir: Path) -> list[Path]:
    written: list[Path] = []
    nl_dir = out_dir / "netlists"
    for flavour, decks in (("ngspice", ngspice_decks()),
                           ("ltspice", ltspice_decks())):
        d = nl_dir / flavour
        d.mkdir(parents=True, exist_ok=True)
        for name, text in decks.items():
            path = d / name
            path.write_text(text, encoding="utf-8")
            written.append(path)

    nl_dir.mkdir(parents=True, exist_ok=True)
    p = nl_dir / "board.net"
    p.write_text(protel_netlist(), encoding="utf-8")
    written.append(p)

    write_csv(out_dir / "bom.csv", C.bom_rows())
    written.append(out_dir / "bom.csv")
    write_csv(out_dir / "VERIFY.csv", C.verify_rows())
    written.append(out_dir / "VERIFY.csv")
    write_csv(out_dir / "compensation_values.csv", D.compensator_summary())
    written.append(out_dir / "compensation_values.csv")
    return written
