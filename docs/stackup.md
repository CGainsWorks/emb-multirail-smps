# Stackup

Four layers, 1.6 mm finished, 100 by 80 mm. Nothing on this board is a
transmission line, so the stackup is chosen for current handling, thermal
spreading and return path quality rather than for impedance control.

**No board has been fabricated.** These are the fabrication notes a board house
would be given, not a record of what one built.

---

## Layers

| layer | copper | function |
|---|---|---|
| L1, top | 2 oz (70 um) | Power components, switch nodes, high current routing. All the switching loops live here. |
| L2 | 1 oz (35 um) | Solid ground. Unbroken under every switching loop, no exceptions. |
| L3 | 1 oz (35 um) | Power planes: VIN, +5V, +3V3, +12V as separate pours. |
| L4, bottom | 2 oz (70 um) | Return copper, thermal spreading, control and feedback routing, connectors. |

```
   L1  2 oz  ------------------------------  power components
             prepreg 0.20 mm
   L2  1 oz  ------------------------------  GND, solid
             core 1.065 mm
   L3  1 oz  ------------------------------  power planes
             prepreg 0.20 mm
   L4  2 oz  ------------------------------  returns, control, connectors
```

Total 1.6 mm nominal.

---

## Why this arrangement

**L1 to L2 is thin, 0.20 mm.** The single most useful thing a four layer
stackup can do for a switching converter is put a solid ground plane as close
as possible under the switching loop. The loop inductance falls roughly with
the separation, and loop inductance is what turns a clean switch node edge into
ringing, overshoot and radiated emissions. Everything else in the stackup gives
way to this.

**The thick core is between L2 and L3.** The two planes that matter for return
current, L2 ground and the L1 power components, are adjacent. The power planes
on L3 are decoupled to L2 through vias and bulk capacitance, not through
plane-to-plane capacitance, so their separation from ground is not critical and
the core can carry the mechanical thickness.

**2 oz on the outer layers.** The +5V stage carries 4.6 A and the input carries
up to 3 A at low line. At 2 oz a 3 mm trace carries 5 A with about 10 degrees
of rise, which is comfortable. It also doubles the copper available for
spreading heat away from the FETs and the inductor, and this board has no
heatsink and no airflow, so spreading is the entire thermal strategy.

**1 oz on the inner layers.** Inner copper is more expensive and the inner
layers here are planes, not current paths. The current density argument does
not apply.

---

## Fabrication notes

| item | value |
|---|---|
| Material | FR-4, Tg 150 or better |
| Finished thickness | 1.6 mm plus or minus 10 % |
| Copper | 2/1/1/2 oz |
| Minimum track and gap | 0.15 mm on signals, 0.25 mm on power |
| Minimum drill | 0.30 mm |
| Via | 0.30 mm drill, 0.60 mm pad, tented on L1 where under components |
| Thermal vias | 0.30 mm, unfilled, under every exposed pad |
| Surface finish | ENIG |
| Soldermask | both sides, green |
| Silkscreen | both sides, white |
| Electrical test | 100 % netlist test against `outputs/netlists/board.net` |
| Impedance control | none required |

## Creepage and clearance

The highest voltage on the board is 40 V, the survivable input excursion. At
that level, IPC-2221 internal-and-uncoated B4 spacing asks for 0.13 mm, which
every minimum gap above already exceeds by a wide margin. No special spacing is
needed anywhere, and there is no isolation barrier.

## What is not specified here

* Panelisation, tooling holes and fiducials. They depend on the assembler.
* Solder paste stencil thickness. Typically 0.12 mm for this mix of packages,
  but it is the assembler's call.
* Any impedance target. There is nothing on this board fast enough to need one.
