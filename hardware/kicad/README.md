# KiCad project

KiCad 8 schematic and four layer board for the supply. KiCad is free and the
EDA tool a hardware team without an Altium licence would use; the brief named
Altium, which is not available here.

**Nothing here has been fabricated, assembled, powered or measured.**

| file | what it is |
|---|---|
| `emb-multirail-smps.kicad_sch` | Root sheet: the four stage sheets below and an overview |
| `input_5v.kicad_sch` | Input terminal, fuse, TVS, differential mode filter, +5V buck (LTC3891) |
| `buck_3v3.kicad_sch` | +3V3 voltage mode buck (TPS54317) and its Type III network |
| `boost_12v.kicad_sch` | +12V synchronous boost (TPS43061) |
| `ldo_outputs.kicad_sch` | +1V8A LDO (LP5912-1.8), its input RC filter, preload and the output terminal |
| `smps.kicad_sym` | Symbols for the two controllers KiCad's library does not ship, drawn from their data sheet pin tables |
| `emb-multirail-smps.kicad_pcb` | Four layer board, 100 by 80 mm, to `docs/stackup.md` |
| `emb-multirail-smps.kicad_pro` | Project, net classes and design rules |
| `emb-multirail-smps.kicad_dru` | One custom rule: pad to pad gaps inside library land patterns |

## Where the values come from

Every part carries a `Basis` field:

* `model`: the value the simulation in `simulation/smps` uses. The inductors,
  shunts, capacitor banks, dividers, compensation networks, the input filter
  and the LDO filter and preload.
* `datasheet`: support parts sized from the controller's data sheet, with
  the equation or table quoted in the part's description or note. Timing
  resistors, bootstrap, soft start, bias and bypass capacitors. These are not
  simulated.
* `choice`: a decision with no equation behind it, such as a pull-up value or
  a 0 ohm link.

Every part also has a real manufacturer part number in its `MPN` field. The
headline ratings of each were checked on the manufacturer's or a
distributor's listing; where the data sheet and the model disagree it is
written down in `outputs/VERIFY.csv`. Nothing has been ordered.

Each feedback divider has a 0603 0 ohm link between the rail and the top of
the divider (R14, R22, R32). Replacing it with 20 ohm gives the injection
point the bring-up Bode measurement needs.

## How it is checked

`scripts/kicad/run_checks.sh` does what CI does, in the pinned
`kicad/kicad:8.0.9` image:

1. `kicad-cli sch erc` with every severity enabled. It has to report nothing
   at all, warnings included.
2. `kicad-cli sch export netlist`, then `scripts/kicad/check_netlist.py`,
   which holds the exported netlist to the simulation: every R, L and C in
   every ngspice deck CI runs is matched to the part it stands for, by value
   (after the DC bias derating the model applies to ceramics) and by the nets
   it joins (after the 0 ohm links are closed); the inductors, shunts and
   capacitor banks are compared with `smps.components`; the compensation
   values with `outputs/compensation_values.csv`; and each regulated rail's
   set point is computed from the selected controller's reference and the
   divider. Change a value in KiCad and CI fails.
3. With `--board`, `kicad-cli pcb drc --schematic-parity`. Errors fail;
   warnings are listed.

## How it was made

The schematic was generated from `simulation/smps/hardware.py` by
`scripts/kicad/gen_schematic.py`, in the label style: every pin has a short
wire and a net label. That makes the connectivity explicit and checkable;
it is less pleasant to read than a schematic drawn by hand. Regenerate it with

    python scripts/kicad/gen_schematic.py --symbols <KiCad symbols directory>

and the check above confirms the result still matches.

The board was placed by `scripts/kicad/gen_pcb.py`, one region per stage with
the switching loop parts in the first row of each. It was routed by
`scripts/kicad/route_board.sh`: plane vias for every ground, VIN, +5V and +3V3
pad, 0.30 mm thermal vias under the exposed pads, Freerouting 2.4.1 for the
rest, power tracks widened afterwards as far as clearance allows and up to
three repair passes that take up whatever DRC objects to and route again.

**The board is not finished.** Five connections are unrouted (STATUS.md lists
them) and neither the generated placement nor the autorouted copper has been
through the review in `docs/layout_rules.md`. DRC is otherwise clean and CI
holds it there.
