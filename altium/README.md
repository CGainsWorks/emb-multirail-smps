# Altium

**There is no Altium project here.**

The brief named Altium, which is not available for this project. The
schematic and the four layer board are in KiCad 8 instead, in
[`../hardware/kicad/`](../hardware/kicad/); CI runs ERC, DRC and a
value by value check of the schematic against the simulation on every push.

For someone who does want to start in Altium:

| file | what it is |
|---|---|
| [`../outputs/netlists/board.net`](../outputs/netlists/board.net) | Protel format netlist from the same data as the KiCad schematic. Altium imports it; footprint names are KiCad's and need mapping. |
| [`../outputs/bom.csv`](../outputs/bom.csv) | Bill of materials with real part numbers. |
| [`../outputs/VERIFY.csv`](../outputs/VERIFY.csv) | Where each selected part's data sheet and the model still disagree. |
| [`../docs/stackup.md`](../docs/stackup.md) | Four layer stackup and fabrication notes. |
| [`../docs/layout_rules.md`](../docs/layout_rules.md) | The constraints a layout has to satisfy for the simulated results to mean anything. |
