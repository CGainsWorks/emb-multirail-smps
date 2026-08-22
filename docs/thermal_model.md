# Thermal model

The crudest model in this repository, and the one whose result matters most,
because a supply that meets every electrical specification and runs too hot is
not a working supply.

**No board exists, no thermocouple has been attached and no thermal camera has
been pointed at anything.** Everything below is arithmetic.

---

## The model

Two resistances per part:

```
Tj = Tambient + Ptotal * Rth(board-ambient) + Ppart * Rth(junction-board)
```

One board-to-ambient resistance shared by everything, because on a small board
in still air the copper is the heatsink and every dissipating part is bolted to
the same one. One junction-to-board resistance per part.

### Board to ambient

```
area            = 2 * 0.100 * 0.080          = 0.0160 m^2   both faces
h_convection    = 8 W/m^2K                   natural convection, vertical
h_radiation     = 6 W/m^2K                   soldermask, emissivity ~0.9, ~350 K
coupled fraction= 0.60
Rth(b-a) = 1 / ((8 + 6) * 0.0160 * 0.60)     = 7.44 K/W
```

The coupled fraction is the honest fudge factor. Not all of a board is at the
same temperature and not all of it is connected to the power stages, so
crediting the full area would be optimistic. Sixty percent is a judgement, not
a measurement, and the sensitivity is direct: a board that only manages 40
percent runs 12 degrees hotter at full load.

### Junction to board

| device | Rth(j-b) assumed |
|---|---|
| Q1, Q2 buck FETs, SON 3x3 with exposed pad | 12 K/W |
| U3 3V3 regulator, VQFN-16 with pad | 18 K/W |
| U5 1V8 LDO, WSON-6 with pad | 20 K/W |
| L1 buck inductor | 25 K/W |
| L2, L3 inductors | 30 K/W |
| Q3, Q4 boost FETs, SOT-23 | 35 K/W |
| Rs1 sense resistor, 2512 | 40 K/W |

All package level assumptions, all on `outputs/VERIFY.csv` to be replaced by
datasheet figures before anything is ordered.

### Attribution of loss to parts

Straightforward except for one term. **Gate drive loss is split evenly between
the two FETs, and that is wrong.** Most of the gate charge is actually
dissipated in the driver stage inside the controller, not in the FET's gate
resistance. Attributing it to the FETs makes the FET predictions pessimistic by
45 mW each on the buck, about half a degree, and makes the controller
prediction optimistic by 90 mW. The controller is not the hot part here so the
error does not change the conclusion, but it would on a design with an
integrated power stage.

---

## Result

At 55 degrees ambient, 36 V input, full load on every rail, from
`test-results/thermal/junction_temperatures.csv`:

```
total board loss   3.33 W
board temperature  79.8 C
hottest junction   Q1 buck high side FET, 94.3 C
next               U5 1V8 LDO, 93.4 C
margin to 125 C    30.7 K
```

Maximum ambient for a 125 degree junction, at full load:

| Vin | max ambient |
|---|---|
| 8 V | 93.3 C |
| 24 V | 89.5 C |
| 36 V | 85.7 C |

against a specification of 55 degrees. The derating curve over load is in
`test-results/thermal/ambient_derating.png`.

Two things worth noticing. The worst case is high line, not low line, because
switching loss scales with input voltage while conduction loss does not. And a
linear regulator dropping 1.5 V at 0.5 A comes within a degree of the switching
FET that carries the whole board, which is worth knowing before somebody
decides the LDO is the small part that can go anywhere.

---

## What this model does not do

**It assumes the board is isothermal.** It is not. There will be a hot spot
under the high side FET and a cool corner near the connectors, and the real
spread across a board like this is 15 to 25 degrees. So:

* the FET junction predictions are **optimistic**, because the copper directly
  under them is hotter than the board average;
* the parts far from the power stages are **pessimistic**;
* the LDO, which is deliberately placed at the far end from the switchers, is
  probably a few degrees better than the 93.4 C above.

**It does not iterate temperature against loss.** Rds(on) rises with
temperature, which raises loss, which raises temperature. The fixed point is a
few degrees above the single pass answer for a board with this much conduction
loss. `docs/loss_model.md` states the same caveat from the other side.

**It has no transient behaviour.** There is no thermal capacitance in the
model, so it says nothing about a short overload or a start-up surge.

**It assumes still air, vertical mounting and no enclosure.** An enclosure
changes the convection coefficient substantially and is the most likely reason
a real measurement would come in worse than this.

---

## What would settle it

A thermal camera and a load. Specifically:

1. Thermocouple on the board near each power stage, one in free air for
   reference.
2. Full load on every rail, at 8, 24 and 36 V, held until stable.
3. Thermal image once stable, with an emissivity reference dot on each package
   being measured.
4. Compare the measured board temperature against 79.8 C at 55 C ambient, and
   each package top
   against the junction prediction minus the package's Rth(j-top).

Until that has been done, the derating table above is a calculation and should
be described as one.
