# Altium

**There is no Altium project here.**

No schematic has been captured, no board has been laid out and no fabrication
data exists. Saying otherwise by leaving a stub project in this directory would
be worse than leaving it empty.

What this repository does provide, for someone who wants to start the schematic:

| file | what it is |
|---|---|
| [`../outputs/netlists/board.net`](../outputs/netlists/board.net) | Protel format netlist. Altium imports this directly and it gives you every part, footprint and net. |
| [`../outputs/bom.csv`](../outputs/bom.csv) | Bill of materials with candidate part numbers, all unverified. |
| [`../outputs/compensation_values.csv`](../outputs/compensation_values.csv) | The compensation network values, generated from the loop design. |
| [`../docs/stackup.md`](../docs/stackup.md) | Four layer stackup and fabrication notes. |
| [`../docs/layout_rules.md`](../docs/layout_rules.md) | The constraints a layout has to satisfy for the simulated results to mean anything. |

Importing the netlist gives correct connectivity. It does not give a schematic
that is pleasant to read, and it does not give placement or routing. Both of
those are the work this repository has not done.
