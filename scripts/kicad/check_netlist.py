#!/usr/bin/env python3
"""Hold the KiCad schematic to the simulation, value by value.

    python scripts/kicad/check_netlist.py hardware/kicad/build/netlist.net

The argument is the netlist ``kicad-cli sch export netlist`` writes from the
committed schematic. Four things are checked and any failure fails the run:

1. **Connectivity.** Every net in the schematic joins exactly the pins
   ``simulation/smps/hardware.py`` says it does and every pin left open is
   one that is meant to be.
2. **Parts.** Every component carries a footprint, a manufacturer and a part
   number and they are the ones in the data.
3. **The ngspice decks.** Every R, L and C in every deck CI runs through
   ngspice is matched to the schematic part or parts it stands for: same
   value, after the DC bias derating the model applies to ceramics, and
   joining the same nets, after the 0 ohm loop injection links are closed.
   Elements with no part behind them (sources, the LISN, ESR and ESL, the
   behavioural comparator) are named as such rather than skipped silently.
4. **The models.** Inductances, shunts, capacitor banks, the LDO filter and
   preload, the compensation table in ``outputs/compensation_values.csv``,
   and the output voltage each controller's reference and divider set.

Nothing here simulates anything. It checks that the schematic someone would
build from is the circuit that was simulated.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "simulation"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sexpr import find, find_all, parse, unq  # noqa: E402
from smps import components as C  # noqa: E402
from smps import hardware as H  # noqa: E402
from smps.spec import rail  # noqa: E402

DECKS = ROOT / "outputs" / "netlists" / "ngspice"
REL = 1e-3          # value tolerance: the decks print six significant figures
SETPOINT_TOL = 0.01

_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0,
       "k": 1e3, "K": 1e3, "M": 1e6}


def parse_value(text: str) -> float:
    """``2.4k``, ``15nF``, ``6.8uH``, ``5m``, ``0`` -> SI float."""
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([pnuµmkKM]?)\s*(F|H|R|ohm|Ω)?\s*", text)
    if not m:
        raise ValueError(f"cannot read a value from {text!r}")
    return float(m.group(1)) * _SI[m.group(2)]


# --------------------------------------------------------------------------
# Netlist
# --------------------------------------------------------------------------

def read_netlist(path: Path):
    top = parse(path.read_text(encoding="utf-8"))[0]
    comps = {}
    for comp in find_all(find(top, "components"), "comp"):
        ref = unq(find(comp, "ref")[1])
        fields = {}
        for f in find_all(find(comp, "fields") or [], "field"):
            name = unq(find(f, "name")[1])
            fields[name] = unq(f[2]) if len(f) > 2 and not isinstance(f[2], list) else ""
        fp = find(comp, "footprint")
        comps[ref] = {"value": unq(find(comp, "value")[1]),
                      "footprint": unq(fp[1]) if fp else "",
                      "fields": fields}
    nets, open_pins = {}, set()
    for net in find_all(find(top, "nets"), "net"):
        name = unq(find(net, "name")[1])
        nodes = [f"{unq(find(n, 'ref')[1])}-{unq(find(n, 'pin')[1])}"
                 for n in find_all(net, "node")]
        if name.startswith("unconnected-("):
            open_pins.update(nodes)
            continue
        nets[name.rsplit("/", 1)[-1]] = sorted(nodes)
    return comps, nets, open_pins


class Report:
    def __init__(self):
        self.failures: list[str] = []
        self.passes = 0

    def check(self, ok: bool, what: str, detail: str = "") -> None:
        if ok:
            self.passes += 1
        else:
            self.failures.append(f"{what}: {detail}" if detail else what)

    def close(self, a: float, b: float, what: str) -> None:
        ok = abs(a - b) <= REL * max(abs(a), abs(b), 1e-30)
        self.check(ok, what, f"schematic {a:.6g} against {b:.6g}")


# --------------------------------------------------------------------------
# 1 and 2: connectivity and parts
# --------------------------------------------------------------------------

def check_connectivity(rep, comps, nets, open_pins):
    want = H.nets()
    for name in sorted(set(want) | set(nets)):
        rep.check(name in nets, f"net {name}", "missing from the schematic")
        rep.check(name in want, f"net {name}", "in the schematic but not in the data")
        if name in nets and name in want:
            rep.check(nets[name] == want[name], f"net {name}",
                      f"schematic {nets[name]} against {want[name]}")
    want_open = {f"{p.ref}-{pin}" for p in H.board()
                 for pin, net in p.pins.items() if net is None}
    rep.check(open_pins == want_open, "open pins",
              f"schematic {sorted(open_pins)} against {sorted(want_open)}")


def check_parts(rep, comps):
    data = H.by_ref()
    real = {r for r in comps if not r.startswith("#")}
    rep.check(real == set(data), "component list",
              f"only in schematic {sorted(real - set(data))}, "
              f"only in data {sorted(set(data) - real)}")
    for ref in sorted(real & set(data)):
        c, p = comps[ref], data[ref]
        f = c["fields"]
        rep.check(bool(c["footprint"]) and c["footprint"] == p.footprint,
                  f"{ref} footprint", f"{c['footprint']!r} against {p.footprint!r}")
        rep.check(bool(f.get("MPN")) and f.get("MPN") == p.mpn,
                  f"{ref} part number", f"{f.get('MPN')!r} against {p.mpn!r}")
        rep.check(bool(f.get("Manufacturer")), f"{ref} manufacturer", "empty")
        if p.nominal is not None:
            rep.close(parse_value(c["value"]), p.nominal, f"{ref} value")


# --------------------------------------------------------------------------
# 3: the ngspice decks
# --------------------------------------------------------------------------

def derate(key):
    return C.CERAMIC_DERATING[key] if key else 1.0


#: deck -> node map, element -> (schematic refs, derating key) and the
#: elements that model something with no part on the board.
DECK_MAP = {
    "comp_buck5_typeii_ac.cir": dict(
        nodes={"out": "+5V", "fb": "FB_5V", "comp": "COMP_5V", "nc": "COMPZ_5V"},
        parts={"Rtop": (["Rt1"], None), "Rbot": (["Rb1"], None),
               "Rc": (["Rc1"], None), "Cc": (["Cc1"], None), "Cp": (["Cp1"], None)},
        model_only={"Vac": "AC stimulus", "Gea": "error amplifier gm",
                    "Ro": "error amplifier output resistance"}),
    "comp_boost12_typeii_ac.cir": dict(
        nodes={"out": "+12V", "fb": "FB_12V", "comp": "COMP_12V", "nc": "COMPZ_12V"},
        parts={"Rtop": (["Rt2"], None), "Rbot": (["Rb3"], None),
               "Rc": (["Rc2"], None), "Cc": (["Cc2"], None), "Cp": (["Cp2"], None)},
        model_only={"Vac": "AC stimulus", "Gea": "error amplifier gm",
                    "Ro": "error amplifier output resistance"}),
    "comp_buck3v3_typeiii_ac.cir": dict(
        nodes={"out": "+3V3", "fb": "FB_3V3", "n3": "N3_3V3", "nf": "NF_3V3",
               "comp": "COMP_3V3"},
        parts={"R1": (["R1"], None), "Rbot": (["Rb2"], None), "R3": (["R3"], None),
               "Cf3": (["Cf3"], None), "Rf": (["Rf2"], None), "Cf1": (["Cf1"], None),
               "Cf2": (["Cf2"], None)},
        model_only={"Vac": "AC stimulus", "Eea": "error amplifier"}),
    "buck3v3_transient.cir": dict(
        nodes={"vin": "+5V", "sw": "SW_3V3", "lx": "+3V3", "out": "+3V3",
               "cx": "GND", "ci": "GND", "fb": "FB_3V3", "n3": "N3_3V3",
               "nf": "NF_3V3", "comp": "COMP_3V3"},
        parts={"L1": (["L2"], None),
               "Cout": (["C7", "C8"], ("22uF", "16V", 3.3)),
               "Cin": (["C18", "C19"], ("10uF", "16V", 5.0)),
               "R1": (["R1"], None), "Rbot": (["Rb2"], None), "R3": (["R3"], None),
               "Cf3": (["Cf3"], None), "Rf": (["Rf2"], None), "Cf1": (["Cf1"], None),
               "Cf2": (["Cf2"], None)},
        model_only={"Vin": "input source", "Rload": "load", "Shs": "high side FET inside U3",
                    "Sls": "low side FET inside U3", "Bgb": "gate logic inside U3",
                    "Rl1": "L2 winding resistance", "Resr": "output capacitor ESR",
                    "Rcin": "input capacitor ESR", "Vramp": "PWM ramp inside U3",
                    "Bpwm": "PWM comparator inside U3", "Bea": "error amplifier inside U3"}),
    "input_filter_ac.cir": dict(
        nodes={"conv": "VIN", "c1a": "GND", "c1b": "GND", "cba": "GND", "cbb": "GND",
               "ldm": "VIN_F", "lead": "VIN_F", "c2a": "GND", "c2b": "GND"},
        parts={"C1": (["C1", "C2"], ("10uF", "50V", 24.0)), "Cb": (["C3"], None),
               "Ldm": (["L4"], None), "C2": (["C12"], None)},
        model_only={"Iconv": "converter input current", "L1esl": "ESL", "R1esr": "ESR",
                    "Lbesl": "ESL", "Rbesr": "ESR", "Rdm": "L4 winding resistance",
                    "L2esl": "ESL", "R2esr": "ESR", "Llisn": "LISN", "Rlisn": "LISN"}),
}


def read_deck(path: Path) -> dict[str, tuple[str, str, str]]:
    """Element name -> (node, node, value text) for every two terminal line."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line[0] in "*." or line.startswith("+"):
            continue
        tok = line.split()
        if len(tok) >= 3 and tok[0][0].upper() in "RCLVIGEBS":
            out[tok[0]] = (tok[1], tok[2], tok[3] if len(tok) > 3 else "")
    return out


class Union:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)


class Schematic:
    """Values and connections as the schematic has them, not as the data does.

    The deck and model checks read from here, so a value edited in KiCad is
    held against the simulation directly.
    """

    def __init__(self, comps, nets):
        self.pins: dict[str, dict[str, str]] = {}
        for net, nodes in nets.items():
            for node in nodes:
                ref, pin = node.rsplit("-", 1)
                self.pins.setdefault(ref, {})[pin] = net
        self.values = {}
        for ref, c in comps.items():
            if ref.startswith("#"):
                continue
            try:
                self.values[ref] = parse_value(c["value"])
            except ValueError:
                pass
        # Close every 0 ohm link: for the circuit they are wire.
        self.u = Union()
        for ref, val in self.values.items():
            if val == 0 and ref[0] == "R" and len(self.pins.get(ref, {})) == 2:
                a, b = self.pins[ref].values()
                self.u.join(a, b)

    def value(self, *refs):
        return sum(self.values[r] for r in refs)

    def nets_of(self, ref):
        return {self.u.find(n) for n in self.pins.get(ref, {}).values()}


def check_decks(rep, sch):
    u = sch.u

    for deck, spec in DECK_MAP.items():
        path = DECKS / deck
        rep.check(path.exists(), f"deck {deck}", "missing")
        if not path.exists():
            continue
        elements = read_deck(path)
        accounted = set(spec["parts"]) | set(spec["model_only"])
        rep.check(set(elements) == accounted, f"deck {deck} elements",
                  f"not accounted for {sorted(set(elements) - accounted)}, "
                  f"expected but absent {sorted(accounted - set(elements))}")
        for name, (refs, dkey) in spec["parts"].items():
            if name not in elements:
                continue
            n1, n2, val = elements[name]
            want = sch.value(*refs) * derate(dkey)
            rep.close(want, float(val), f"{deck} {name} = {'+'.join(refs)}")
            mapped = {u.find(spec["nodes"].get(n, "GND" if n == "0" else f"?{n}"))
                      for n in (n1, n2)}
            for r in refs:
                rep.check(sch.nets_of(r) == mapped, f"{deck} {name} = {r} nets",
                          f"part joins {sorted(sch.nets_of(r))}, deck element "
                          f"joins {sorted(mapped)}")


# --------------------------------------------------------------------------
# 4: the models
# --------------------------------------------------------------------------

def check_models(rep, sch):
    v = sch.value
    D = C.CERAMIC_DERATING
    checks = [
        ("+5V inductor L1", v("L1"), C.BUCK5["L_H"]),
        ("+5V shunt Rs1", v("Rs1"), C.BUCK5["r_sense_ohm"]),
        ("+5V output bank C4-C6", v("C4", "C5", "C6") * D[("22uF", "25V", 5.0)],
         C.BUCK5["Cout_F"]),
        ("+5V input bank C1,C2", v("C1", "C2") * D[("10uF", "50V", 24.0)],
         C.BUCK5["Cin_F"]),
        ("+5V bulk C3", v("C3"), C.BUCK5["Cbulk_F"]),
        ("+3V3 inductor L2", v("L2"), C.BUCK3V3["L_H"]),
        ("+3V3 output bank C7,C8", v("C7", "C8") * D[("22uF", "16V", 3.3)],
         C.BUCK3V3["Cout_F"]),
        ("+3V3 input bank C18,C19", v("C18", "C19") * D[("10uF", "16V", 5.0)],
         C.BUCK3V3["Cin_F"]),
        ("+12V inductor L3", v("L3"), C.BOOST12["L_H"]),
        ("+12V shunt Rs2", v("Rs2"), C.BOOST12["r_sense_ohm"]),
        ("+12V output bank C9,C10", v("C9", "C10") * D[("22uF", "25V", 12.0)],
         C.BOOST12["Cout_F"]),
        ("+12V input C23", v("C23") * D[("10uF", "16V", 5.0)], C.BOOST12["Cin_F"]),
        ("+1V8A output C11", v("C11") * D[("10uF", "6.3V", 1.8)], C.LDO1V8["Cout_F"]),
        ("+1V8A input C13", v("C13") * D[("10uF", "16V", 5.0)], C.LDO1V8["Cin_F"]),
        ("+1V8A input filter Rf1", v("Rf1"), C.LDO1V8["input_rc_r_ohm"]),
        ("+1V8A preload Rpl1", v("Rpl1"), C.LDO1V8["preload_r_ohm"]),
    ]
    for what, a, b in checks:
        rep.close(a, b, what)

    # The compensation table the README and the docs quote.
    with (ROOT / "outputs" / "compensation_values.csv").open(encoding="utf-8") as fh:
        rows = {r["rail"]: r for r in csv.DictReader(fh)}
    table = {
        "+5V": {"Rc_ohm": "Rc1", "Cc_F": "Cc1", "Cp_F": "Cp1", "Rtop_ohm": "Rt1",
                "Rbot_ohm": "Rb1"},
        "+12V": {"Rc_ohm": "Rc2", "Cc_F": "Cc2", "Cp_F": "Cp2", "Rtop_ohm": "Rt2",
                 "Rbot_ohm": "Rb3"},
        "+3V3": {"R1_ohm": "R1", "Rbot_ohm": "Rb2", "R3_ohm": "R3", "Rf_ohm": "Rf2",
                 "Cf1_F": "Cf1", "Cf2_F": "Cf2", "Cf3_F": "Cf3"},
    }
    for rail_name, cols in table.items():
        for col, ref in cols.items():
            rep.close(v(ref), float(rows[rail_name][col]),
                      f"compensation_values.csv {rail_name} {col} = {ref}")

    # The set point each controller's reference and divider give.
    models = {"+5V": C.BUCK5, "+3V3": C.BUCK3V3, "+12V": C.BOOST12}
    for ctl in H.controllers():
        rep.close(ctl.v_ref_v, models[ctl.rail]["v_ref_v"],
                  f"{ctl.ref} reference used by the model ({ctl.source})")
        v_out = ctl.v_ref_v * (1 + v(*ctl.divider_top) / v(ctl.divider_bottom))
        target = rail(ctl.rail).v_out_v
        rep.check(abs(v_out / target - 1) <= SETPOINT_TOL,
                  f"{ctl.rail} set point", f"{v_out:.4f} V against {target} V")
        print(f"  {ctl.rail:5s} set point {v_out:.4f} V from {ctl.ref} "
              f"Vref {ctl.v_ref_v} V and the divider, target {target} V")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    comps, nets, open_pins = read_netlist(Path(sys.argv[1]))
    rep = Report()
    print(f"schematic: {len([c for c in comps if not c.startswith('#')])} parts, "
          f"{len(nets)} nets, {len(open_pins)} pins deliberately open")
    check_connectivity(rep, comps, nets, open_pins)
    check_parts(rep, comps)
    sch = Schematic(comps, nets)
    check_decks(rep, sch)
    check_models(rep, sch)
    print(f"{rep.passes} checks passed, {len(rep.failures)} failed")
    for f in rep.failures:
        print(f"  FAIL {f}")
    return 1 if rep.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
