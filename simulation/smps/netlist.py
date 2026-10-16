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
from . import hardware as H
from .spice import ltspice_decks, ngspice_decks


def _fmt(x: float) -> str:
    """SPICE friendly engineering notation."""
    return f"{x:.6g}"


# --------------------------------------------------------------------------
# Protel netlist for Altium
# --------------------------------------------------------------------------

# The connection list is the KiCad schematic's, from smps.hardware, so the
# Protel file, the schematic and the board cannot disagree. Footprints are the
# KiCad library names; Altium users map them on import.

#: (designator, footprint, comment)
SCH_PARTS = [(p.ref, p.footprint.split(":")[1], f"{p.value} {p.mpn}")
             for p in H.board()]

#: net name -> list of "Designator-pin"
SCH_NETS = H.nets()


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

def write_lf(path: Path, text: str) -> None:
    """Write text with LF line endings on every platform.

    ``Path.write_text`` translates newlines to CRLF on Windows, which turns
    every regeneration there into a whole file diff."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        write_lf(path, "")
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
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
            write_lf(path, text)
            written.append(path)

    nl_dir.mkdir(parents=True, exist_ok=True)
    p = nl_dir / "board.net"
    write_lf(p, protel_netlist())
    written.append(p)

    write_csv(out_dir / "bom.csv", H.bom_rows())
    written.append(out_dir / "bom.csv")
    write_csv(out_dir / "VERIFY.csv", C.verify_rows())
    written.append(out_dir / "VERIFY.csv")
    write_csv(out_dir / "compensation_values.csv", D.compensator_summary())
    written.append(out_dir / "compensation_values.csv")
    return written
