#!/usr/bin/env python3
"""Write the KiCad 8 schematic from ``simulation/smps/hardware.py``.

    python scripts/kicad/gen_schematic.py --symbols <KiCad symbol library dir>

The symbol directory is KiCad's own library, ``/usr/share/kicad/symbols`` in
the ``kicad/kicad`` container. The script copies each library symbol it uses
into the schematic, the way KiCad itself does and writes the two controller
symbols KiCad does not ship to ``hardware/kicad/smps.kicad_sym``.

The schematic is drawn in the label style: every pin gets a short wire and a
net label, so connectivity is explicit and checkable and nothing depends on
two wires happening to meet. It is regenerated whenever the design changes
and committed; ``scripts/kicad/check_netlist.py`` holds the committed copy to
the data and to the simulation.
"""

from __future__ import annotations

import argparse
import copy
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "simulation"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sexpr import dumps, find, find_all, num, parse, q, unq  # noqa: E402
from smps import hardware as H  # noqa: E402

OUT = ROOT / "hardware" / "kicad"
NS = uuid.UUID("6f1d2c3a-5b4e-4c7d-9a8b-2e1f0d3c4b5a")
DATE = "2026-10-16"
GRID = 2.54
STUB = 2.54


def uid(*key: str) -> str:
    return str(uuid.uuid5(NS, "/".join(key)))


def snap(x: float) -> float:
    return round(x / 1.27) * 1.27


# --------------------------------------------------------------------------
# Custom symbols for the two controllers KiCad's library does not have
# --------------------------------------------------------------------------

#: name -> (description, datasheet, [(number, name, type, side, slot, hidden)])
#: side is L, R or B; slot counts down from the top (L/R) or across (B).
CUSTOM = {
    "LTC3891xFE": (
        "60 V low IQ synchronous step-down controller, peak current mode, "
        "TSSOP-20 with exposed pad",
        "https://www.analog.com/media/en/technical-documentation/data-sheets/3891fc.pdf",
        [
            ("17", "VIN", "power_in", "L", 0, False),
            ("4", "RUN", "input", "L", 1, False),
            ("15", "EXTVCC", "power_in", "L", 2, False),
            ("1", "PLLIN/MODE", "input", "L", 4, False),
            ("18", "ILIM", "input", "L", 5, False),
            ("20", "FREQ", "passive", "L", 6, False),
            ("19", "TRACK/SS", "passive", "L", 7, False),
            ("8", "ITH", "output", "L", 9, False),
            ("7", "VFB", "input", "L", 10, False),
            ("12", "BOOST", "passive", "R", 0, False),
            ("10", "TG", "output", "R", 1, False),
            ("11", "SW", "passive", "R", 2, False),
            ("13", "BG", "output", "R", 4, False),
            ("14", "INTVCC", "power_out", "R", 6, False),
            ("6", "SENSE+", "input", "R", 8, False),
            ("5", "SENSE-", "input", "R", 9, False),
            ("9", "PGOOD", "open_collector", "R", 10, False),
            ("2", "SGND", "power_in", "B", 0, False),
            ("3", "SGND", "passive", "B", 0, True),
            ("16", "PGND", "power_in", "B", 2, False),
            ("21", "EP", "passive", "B", 4, False),
        ],
    ),
    "TPS54317xRHF": (
        "3 to 6 V input, 3 A synchronous step-down converter, voltage mode, "
        "integrated FETs, QFN-24 4x5 mm",
        "https://www.ti.com/lit/ds/symlink/tps54317.pdf",
        [
            ("15", "VIN", "power_in", "L", 0, False),
            ("16", "VIN", "passive", "L", 0, True),
            ("17", "VIN", "passive", "L", 0, True),
            ("18", "VBIAS", "power_out", "L", 2, False),
            ("19", "SS/ENA", "passive", "L", 3, False),
            ("20", "SYNC", "input", "L", 4, False),
            ("22", "RT", "passive", "L", 5, False),
            ("1", "COMP", "output", "L", 7, False),
            ("24", "VSENSE", "input", "L", 8, False),
            ("3", "BOOT", "passive", "R", 0, False),
            ("4", "PH", "passive", "R", 1, False),
            ("5", "PH", "passive", "R", 1, True),
            ("6", "PH", "passive", "R", 1, True),
            ("7", "PH", "passive", "R", 1, True),
            ("8", "PH", "passive", "R", 1, True),
            ("9", "PH", "passive", "R", 1, True),
            ("2", "PWRGD", "open_collector", "R", 3, False),
            ("10", "NC", "no_connect", "R", 6, False),
            ("21", "NC", "no_connect", "R", 7, False),
            ("11", "PGND", "power_in", "B", 0, False),
            ("12", "PGND", "passive", "B", 0, True),
            ("13", "PGND", "passive", "B", 0, True),
            ("14", "PGND", "passive", "B", 0, True),
            ("23", "AGND", "power_in", "B", 2, False),
            ("25", "EP", "passive", "B", 4, False),
        ],
    ),
}


def _effects(size=1.27, hide=False, justify=None):
    e = ["effects", ["font", ["size", num(size), num(size)]]]
    if justify:
        e.append(["justify", *justify])
    if hide:
        e.append(["hide", "yes"])
    return e


def _prop(name, value, x, y, hide=False, justify=None, angle=0):
    return ["property", q(name), q(value), ["at", num(x), num(y), num(angle)],
            _effects(hide=hide, justify=justify)]


def custom_symbol(name: str, cache_name: str | None = None) -> list:
    desc, datasheet, pins = CUSTOM[name]
    rows = max(p[4] for p in pins if p[3] in "LR") + 1
    half_w = 10.16
    top = GRID * (rows // 2 + 1)
    bottom = top - GRID * (rows + 1)
    sym = ["symbol", q(cache_name or name),
           ["pin_names", ["offset", "1.016"]],
           ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
           _prop("Reference", "U", -half_w, top + 1.27, justify=["left"]),
           _prop("Value", name, half_w, top + 1.27, justify=["right"]),
           _prop("Footprint", "", 0, 0, hide=True),
           _prop("Datasheet", datasheet, 0, 0, hide=True),
           _prop("Description", desc, 0, 0, hide=True)]
    body = ["symbol", q(f"{name}_0_1"),
            ["rectangle", ["start", num(-half_w), num(top)],
             ["end", num(half_w), num(bottom - GRID * 2)],
             ["stroke", ["width", "0.254"], ["type", "default"]],
             ["fill", ["type", "background"]]]]
    unit = ["symbol", q(f"{name}_1_1")]
    for number, pname, ptype, side, slot, hidden in pins:
        if side == "L":
            x, y, rot = -half_w - GRID, top - GRID * (slot + 1), 0
        elif side == "R":
            x, y, rot = half_w + GRID, top - GRID * (slot + 1), 180
        else:
            x, y, rot = -half_w + GRID * (slot + 2), bottom - GRID * 2 - GRID, 90
        pin = ["pin", ptype, "line", ["at", num(x), num(y), num(rot)],
               ["length", num(GRID)]]
        if hidden:
            pin.append("hide")      # KiCad 8 writes a bare token on pins
        pin += [["name", q(pname), _effects()], ["number", q(number), _effects()]]
        unit.append(pin)
    sym += [body, unit]
    return sym


def write_custom_library() -> None:
    lib = ["kicad_symbol_lib", ["version", "20231120"], ["generator", q("gen_schematic")],
           ["generator_version", q("8.0")]]
    for name in CUSTOM:
        lib.append(custom_symbol(name))
    (OUT / "smps.kicad_sym").write_text(dumps(lib) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Library symbols, flattened into the schematic cache
# --------------------------------------------------------------------------

class Library:
    def __init__(self, symbol_dir: Path):
        self.dir = symbol_dir
        self._libs: dict[str, dict[str, list]] = {}

    def _lib(self, nick: str) -> dict[str, list]:
        if nick not in self._libs:
            text = (self.dir / f"{nick}.kicad_sym").read_text(encoding="utf-8")
            top = parse(text)[0]
            self._libs[nick] = {unq(s[1]): s for s in find_all(top, "symbol")}
        return self._libs[nick]

    def flat(self, lib_id: str) -> list:
        nick, name = lib_id.split(":")
        if nick == "smps":
            return custom_symbol(name, lib_id)
        syms = self._lib(nick)
        sym = syms[name]
        ext = find(sym, "extends")
        if ext is None:
            out = copy.deepcopy(sym)
            out[1] = q(lib_id)
            return out
        parent = unq(ext[1])
        base = self.flat(f"{nick}:{parent}")
        out = [base[0], q(lib_id)]
        child_props = find_all(sym, "property")
        for item in base[2:]:
            if isinstance(item, list) and item[0] == "property":
                continue
            if isinstance(item, list) and item[0] == "symbol":
                unit = copy.deepcopy(item)
                unit[1] = q(unq(unit[1]).replace(parent, name, 1))
                out.append(unit)
                continue
            out.append(item)
        # Properties go before the unit symbols, as KiCad writes them.
        first_unit = next(i for i, it in enumerate(out)
                          if isinstance(it, list) and it[0] == "symbol")
        for k, prop in enumerate(child_props):
            out.insert(first_unit + k, copy.deepcopy(prop))
        return out


def pin_table(flat_symbol: list) -> list[dict]:
    pins = []

    def walk(node):
        for it in node:
            if isinstance(it, list):
                if it[0] == "pin":
                    at = find(it, "at")
                    d = {"type": it[1], "x": float(at[1]), "y": float(at[2]),
                         "rot": int(float(at[3])) if len(at) > 3 else 0,
                         "number": unq(find(it, "number")[1]),
                         "hidden": any((isinstance(s, list) and s[0] == "hide")
                                       or s == "hide" for s in it)}
                    pins.append(d)
                else:
                    walk(it)
    walk(flat_symbol)
    return pins


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

DIRS = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}   # pin rot -> outward, screen
LABEL_ANGLE = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}
GND_ROT = {(0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}


class Sheet:
    def __init__(self, stem, title, page, lib, global_nets, root_uuid, sheet_uuid):
        self.stem, self.title, self.page = stem, title, page
        self.lib = lib
        self.global_nets = global_nets
        self.path = f"/{root_uuid}/{sheet_uuid}"
        self.items: list = []
        self.used: dict[str, list] = {}
        self.n = 0

    def _id(self, *k):
        self.n += 1
        return uid(self.stem, *k, str(self.n))

    def wire(self, a, b):
        self.items.append(["wire", ["pts", ["xy", num(a[0]), num(a[1])],
                                    ["xy", num(b[0]), num(b[1])]],
                           ["stroke", ["width", "0"], ["type", "default"]],
                           ["uuid", q(self._id("w"))]])

    def label(self, net, at, d):
        ang = LABEL_ANGLE[d]
        just = ["left", "bottom"] if ang in (0, 90) else ["right", "bottom"]
        if net in self.global_nets:
            gj = ["left"] if ang in (0, 90) else ["right"]
            self.items.append(["global_label", q(net), ["shape", "passive"],
                               ["at", num(at[0]), num(at[1]), num(ang)],
                               ["fields_autoplaced", "yes"], _effects(justify=gj),
                               ["uuid", q(self._id("g", net))],
                               ["property", q("Intersheetrefs"), q("${INTERSHEET_REFS}"),
                                ["at", num(at[0]), num(at[1]), num(ang)],
                                _effects(hide=True, justify=gj)]])
        else:
            self.items.append(["label", q(net), ["at", num(at[0]), num(at[1]), num(ang)],
                               ["fields_autoplaced", "yes"], _effects(justify=just),
                               ["uuid", q(self._id("l", net))]])

    def no_connect(self, at):
        self.items.append(["no_connect", ["at", num(at[0]), num(at[1])],
                           ["uuid", q(self._id("nc"))]])

    def text(self, body, x, y, size=1.27):
        self.items.append(["text", q(body), ["exclude_from_sim", "no"],
                           ["at", num(x), num(y), "0"],
                           _effects(size=size, justify=["left", "top"]),
                           ["uuid", q(self._id("t"))]])

    def symbol(self, lib_id, ref, value, x, y, footprint="", fields=(), rot=0,
               in_bom=True, power=False):
        flat = self.lib.flat(lib_id)
        self.used[lib_id] = flat
        pins = pin_table(flat)
        sym_uuid = uid(self.stem, "sym", ref)
        lib_nodes = {unq(p[1]): p for p in find_all(flat, "property")}

        def placed(name, val):
            # Where the library puts the field, moved to this symbol.
            node = copy.deepcopy(lib_nodes[name])
            node[2] = q(val)
            at = find(node, "at")
            at[1] = num(x + float(at[1]))
            at[2] = num(y - float(at[2]))
            return node

        def text_of(name):
            return unq(lib_nodes[name][2]) if name in lib_nodes else ""

        props = [placed("Reference", ref), placed("Value", value),
                 _prop("Footprint", footprint, x, y, hide=True),
                 _prop("Datasheet", text_of("Datasheet"), x, y, hide=True),
                 _prop("Description", text_of("Description"), x, y, hide=True)]
        for name, val in fields:
            props.append(_prop(name, val, x, y, hide=True))
        node = ["symbol", ["lib_id", q(lib_id)], ["at", num(x), num(y), num(rot)],
                ["unit", "1"], ["exclude_from_sim", "no"],
                ["in_bom", "yes" if in_bom else "no"], ["on_board", "no" if power else "yes"],
                ["dnp", "no"], ["uuid", q(sym_uuid)], *props]
        for p in sorted({p["number"] for p in pins}, key=lambda s: (len(s), s)):
            node.append(["pin", q(p), ["uuid", q(uid(self.stem, "pin", ref, p))]])
        node.append(["instances", ["project", q(H.PROJECT),
                                   ["path", q(self.path), ["reference", q(ref)],
                                    ["unit", "1"]]]])
        self.items.append(node)
        return pins, sym_uuid

    def power(self, lib_id, at, rot, counter):
        ref = f"#PWR{counter:03d}" if "GND" in lib_id else f"#FLG{counter:03d}"
        self.symbol(lib_id, ref, "GND" if "GND" in lib_id else "PWR_FLAG",
                    at[0], at[1], rot=rot, in_bom=False, power=True)

    def connect(self, at, d, net, counters):
        end = (at[0] + d[0] * STUB, at[1] + d[1] * STUB)
        self.wire(at, end)
        if net == "GND":
            counters["pwr"] += 1
            self.power("power:GND", end, GND_ROT[d], counters["pwr"])
        else:
            self.label(net, end, d)

    def place_part(self, part, x, y, counters):
        fields = [("MPN", part.mpn), ("Manufacturer", part.manufacturer),
                  ("Basis", part.basis)]
        if part.note:
            fields.append(("Note", part.note))
        pins, _ = self.symbol(part.symbol, part.ref, part.value, x, y,
                              part.footprint, fields)
        by_loc: dict[tuple, list] = {}
        for p in pins:
            loc = (snap(x + p["x"]), snap(y - p["y"]))
            by_loc.setdefault(loc, []).append(p)
        for loc, group in by_loc.items():
            nets = {part.pins.get(p["number"], "<missing>") for p in group}
            if "<missing>" in nets:
                missing = [p["number"] for p in group
                           if p["number"] not in part.pins and not p["hidden"]]
                if missing:
                    raise SystemExit(f"{part.ref}: pins {missing} have no net")
                nets.discard("<missing>")
            if len(nets) != 1:
                raise SystemExit(f"{part.ref}: stacked pins at {loc} disagree: {nets}")
            net = nets.pop()
            visible = [p for p in group if not p["hidden"]]
            if not visible:
                continue
            d = DIRS[visible[0]["rot"]]
            if net is None:
                # A pin KiCad already knows is not connected needs no flag.
                if any(p["type"] != "no_connect" for p in visible):
                    self.no_connect(loc)
            else:
                self.connect(loc, d, net, counters)

    def flag(self, net, x, y, counters):
        counters["flg"] += 1
        self.power("power:PWR_FLAG", (x, y), 0, counters["flg"])
        self.connect((x, y), (0, 1), net, counters)

    def write(self, root_uuid):
        lib_symbols = ["lib_symbols", *self.used.values()]
        doc = ["kicad_sch", ["version", "20231120"], ["generator", q("eeschema")],
               ["generator_version", q("8.0")], ["uuid", q(uid(self.stem, "file"))],
               ["paper", q("A3")],
               ["title_block", ["title", q(self.title)], ["date", q(DATE)],
                ["rev", q("A")], ["company", q("CGainsWorks")],
                ["comment", "1", q("Generated from simulation/smps/hardware.py by "
                                   "scripts/kicad/gen_schematic.py")],
                ["comment", "2", q("Not fabricated, not assembled, not measured")]],
               lib_symbols, *self.items]
        (OUT / f"{self.stem}.kicad_sch").write_text(dumps(doc) + "\n",
                                                    encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------

def extents(pins):
    xs = [p["x"] for p in pins] or [0]
    ys = [-p["y"] for p in pins] or [0]
    return min(xs), max(xs), min(ys), max(ys)


def layout_sheet(sheet: Sheet, parts, flags, notes, counters):
    ics = [p for p in parts if p.ref.startswith("U")]
    rest = [p for p in parts if not p.ref.startswith("U")]
    x, y = 60.96, 50.8
    tallest = 0.0
    for p in ics:
        x0, x1, y0, y1 = extents(pin_table(sheet.lib.flat(p.symbol)))
        px = snap(x - x0 + 30)
        sheet.place_part(p, px, snap(y - y0 + 10), counters)
        x = px + x1 + 45
        tallest = max(tallest, y1 - y0)
    y = snap(y + tallest + 45) if ics else y
    x = 30.48
    for p in rest:
        x0, x1, y0, y1 = extents(pin_table(sheet.lib.flat(p.symbol)))
        w = max(22.86, (x1 - x0) + 22.86)
        if x + w > 390:
            x = 30.48
            y = snap(y + 45.72)
        sheet.place_part(p, snap(x - x0 + 8), snap(y), counters)
        x += w
    fx = 30.48
    fy = snap(y + 38.1)
    for net in flags:
        sheet.flag(net, fx, fy, counters)
        fx += 22.86
    if notes:
        sheet.text("\n".join(notes), 223.52, 22.86)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=Path, required=True,
                    help="KiCad symbol library directory")
    args = ap.parse_args()
    lib = Library(args.symbols)
    OUT.mkdir(parents=True, exist_ok=True)
    write_custom_library()

    parts = H.board()
    sheets_of_net: dict[str, set] = {}
    for p in parts:
        for net in p.pins.values():
            if net:
                sheets_of_net.setdefault(net, set()).add(p.sheet)
    global_nets = {n for n, s in sheets_of_net.items() if len(s) > 1 and n != "GND"}

    # Nets with a power input pin and nothing driving them get a PWR_FLAG.
    # One flag per net, on the first sheet the net appears on. A second flag
    # on the same net is two power outputs shorted together as far as ERC is
    # concerned, so it is an error rather than belt and braces.
    kinds: dict[str, set] = {}
    first_sheet: dict[str, str] = {}
    for p in parts:
        pins = pin_table(lib.flat(p.symbol))
        for pin in pins:
            net = p.pins.get(pin["number"])
            if net:
                kinds.setdefault(net, set()).add(pin["type"])
                first_sheet.setdefault(net, p.sheet)
    flagged = sorted((first_sheet[n], n) for n, t in kinds.items()
                     if "power_in" in t and "power_out" not in t)

    root_uuid = uid("root")
    sheet_uuids = {stem: uid("sheet", stem) for stem, _ in H.SHEETS}
    counters = {"pwr": 0, "flg": 0}
    for page, (stem, title) in enumerate(H.SHEETS, start=2):
        sh = Sheet(stem, title, page, lib, global_nets, root_uuid, sheet_uuids[stem])
        mine = [p for p in parts if p.sheet == stem]
        notes = [f"{p.ref}: {p.note}" for p in mine if p.note]
        notes += [f"{p.ref} {p.value}: {p.description}" for p in mine
                  if p.basis == "datasheet" and not p.ref.startswith("U")]
        layout_sheet(sh, mine, [n for s, n in flagged if s == stem],
                     notes, counters)
        sh.write(root_uuid)

    write_root(root_uuid, sheet_uuids)
    write_project(root_uuid, sheet_uuids)
    print(f"wrote {len(H.SHEETS) + 1} sheets, {len(parts)} parts, "
          f"{len(H.nets())} nets, {len(global_nets)} global, flags on {flagged}")
    return 0


#: Net classes, from docs/stackup.md: 0.15 mm minimum track and gap on
#: signals and 0.2 mm gap on power. Power tracks start at 0.25 mm so they can
#: enter a 0.5 mm pitch QFN pad without crowding its neighbours; the routing
#: script then widens every power segment as far as the clearance allows.
#: Ground is not a class of its own: it is the In1 plane and the outer pours.
NET_CLASSES = [
    {"name": "Default", "clearance": 0.15, "track_width": 0.2,
     "via_diameter": 0.6, "via_drill": 0.3},
    {"name": "Power", "clearance": 0.2, "track_width": 0.25,
     "via_diameter": 0.6, "via_drill": 0.3},
]
POWER_PATTERNS = ["*VIN*", "+5V", "+3V3", "+12V", "*+1V8A", "*SW_*", "*SNS_*",
                  "*LDO_IN"]


def write_project(root_uuid, sheet_uuids):
    import json
    classes = []
    for c in NET_CLASSES:
        cls = {"bus_width": 12, "clearance": c["clearance"], "diff_pair_gap": 0.25,
               "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "line_style": 0,
               "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": c["name"],
               "pcb_color": "rgba(0, 0, 0, 0.000)",
               "schematic_color": "rgba(0, 0, 0, 0.000)",
               "track_width": c["track_width"], "via_diameter": c["via_diameter"],
               "via_drill": c["via_drill"], "wire_width": 6}
        classes.append(cls)
    pro = {
        "board": {
            "design_settings": {
                "defaults": {"board_outline_line_width": 0.1,
                             "copper_line_width": 0.2, "silk_line_width": 0.12,
                             "silk_text_size_h": 1.0, "silk_text_size_v": 1.0,
                             "silk_text_thickness": 0.15},
                "meta": {"version": 2},
                "rules": {
                    "min_clearance": 0.15, "min_connection": 0.0,
                    "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.25,
                    "min_hole_to_hole": 0.25, "min_microvia_diameter": 0.2,
                    "min_microvia_drill": 0.1, "min_resolved_spokes": 1,
                    "min_silk_clearance": 0.0, "min_text_height": 0.8,
                    "min_text_thickness": 0.12, "min_through_hole_diameter": 0.3,
                    "min_track_width": 0.15, "min_via_annular_width": 0.13,
                    "min_via_diameter": 0.6, "solder_mask_to_copper_clearance": 0.0,
                    "use_height_for_length_calcs": True, "allow_blind_buried_vias": False,
                    "allow_microvias": False, "max_error": 0.005,
                },
                "track_widths": [0.0, 0.2, 0.4, 0.8, 1.5, 2.5],
                "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                                   {"diameter": 0.6, "drill": 0.3}],
            },
        },
        "meta": {"filename": f"{H.PROJECT}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": classes,
            "meta": {"version": 3},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [{"netclass": "Power", "pattern": p}
                                  for p in POWER_PATTERNS],
        },
        "schematic": {"meta": {"version": 1}},
        "sheets": [[root_uuid, "Root"]] + [[sheet_uuids[s], s] for s, _ in H.SHEETS],
        "text_variables": {},
    }
    (OUT / f"{H.PROJECT}.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n",
                                                encoding="utf-8", newline="\n")
    (OUT / "sym-lib-table").write_text(
        "(sym_lib_table\n  (version 7)\n"
        '  (lib (name "smps")(type "KiCad")(uri "${KIPRJMOD}/smps.kicad_sym")'
        '(options "")(descr "Controllers KiCad does not ship"))\n)\n',
        encoding="utf-8", newline="\n")


def write_root(root_uuid, sheet_uuids):
    items = []
    for i, (stem, title) in enumerate(H.SHEETS):
        x, y = 30.48 + i * 96.52, 60.96
        su = sheet_uuids[stem]
        items.append(["sheet", ["at", num(x), num(y)], ["size", "81.28", "30.48"],
                      ["fields_autoplaced", "yes"],
                      ["stroke", ["width", "0.1524"], ["type", "solid"]],
                      ["fill", ["color", "0", "0", "0", "0.0000"]],
                      ["uuid", q(su)],
                      ["property", q("Sheetname"), q(stem),
                       ["at", num(x), num(y - 0.7116), "0"],
                       _effects(justify=["left", "bottom"])],
                      ["property", q("Sheetfile"), q(f"{stem}.kicad_sch"),
                       ["at", num(x), num(y + 31.0484), "0"],
                       _effects(justify=["left", "top"])],
                      ["instances", ["project", q(H.PROJECT),
                                     ["path", q(f"/{root_uuid}"), ["page", q(str(i + 2))]]]]])
    overview = (
        "Four rail supply, 8 to 36 V in: +5V synchronous buck (LTC3891), +3V3 voltage\n"
        "mode buck from +5V (TPS54317), +12V synchronous boost from +5V (TPS43061) and a\n"
        "+1V8A low noise LDO from +3V3 (LP5912-1.8).\n\n"
        "Every value marked Basis = model is the one the simulation in simulation/smps uses,\n"
        "and scripts/kicad/check_netlist.py fails CI if the two disagree. Values marked\n"
        "datasheet are sized from the controller data sheet and are not simulated.\n\n"
        "Nothing on these sheets has been built or measured."
    )
    items.append(["text", q(overview), ["exclude_from_sim", "no"],
                  ["at", "30.48", "114.3", "0"],
                  _effects(size=1.778, justify=["left", "top"]),
                  ["uuid", q(uid("root", "overview"))]])
    doc = ["kicad_sch", ["version", "20231120"], ["generator", q("eeschema")],
           ["generator_version", q("8.0")], ["uuid", q(root_uuid)], ["paper", q("A3")],
           ["title_block", ["title", q("Multi-rail switch-mode power supply")],
            ["date", q(DATE)], ["rev", q("A")], ["company", q("CGainsWorks")],
            ["comment", "1", q("Generated from simulation/smps/hardware.py by "
                               "scripts/kicad/gen_schematic.py")],
            ["comment", "2", q("Not fabricated, not assembled, not measured")]],
           ["lib_symbols"], *items,
           ["sheet_instances", ["path", q("/"), ["page", q("1")]]]]
    (OUT / f"{H.PROJECT}.kicad_sch").write_text(dumps(doc) + "\n", encoding="utf-8",
                                                newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
