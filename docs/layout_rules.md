# Layout rules

**No layout exists.** This file is the constraint set a layout would have to
satisfy, written down before the layout is started rather than reconstructed
afterwards. It is also the honest boundary of this project: everything in
`test-results/` assumes a layout that meets these rules, and a layout that does
not meet them will not behave like the simulations.

---

## 1. The rules that are not negotiable

### 1.1 The high frequency input loop

For each switching stage, the loop carrying the pulsed current is:

* **buck**: input capacitor positive terminal, high side FET drain, high side
  FET source, low side FET drain, low side FET source, input capacitor negative
  terminal.
* **boost**: output capacitor positive terminal, synchronous rectifier, low
  side FET, output capacitor negative terminal.

That loop is the one that carries a current with nanosecond edges. Its area
sets the loop inductance, and the loop inductance sets the switch node
overshoot, the ringing frequency, and most of what a near field probe will
find.

Rules:

* The ceramic input capacitors sit on the same layer as the FETs, within 2 mm,
  with their own vias to L2 ground rather than sharing the FET's.
* The loop is closed on L1 and L2 only. It never uses L3 or L4.
* L2 under the loop is unbroken. Not a single via antipad chain, not a single
  track.
* Target loop area under 25 mm squared.

### 1.2 The switch node

The switch node is the aggressor for everything else on the board.

* As small as it can be while still carrying the current. Copper area on a
  switch node is capacitance to everything nearby, and it radiates.
* Never on an inner layer. It is not shielded there, it is coupled to both
  planes.
* No feedback, compensation or current sense track routed under it or beside
  it on any layer.

### 1.3 The feedback divider and compensation network

* Placed at the controller, not at the output. The FB pin is the highest
  impedance node on the board and the track to it is an antenna.
* The divider's sense point is a separate track from the point of load, run as
  a quiet route on L4 with ground either side.
* The compensation components share a local ground that returns to the
  controller's ground pin by the shortest path, before joining the power
  ground.

### 1.4 Current sense

* The 5 mOhm shunt is a four terminal part. The sense pair comes off the sense
  terminals, not off the power pads, and runs as a tight differential pair to
  the amplifier.
* The amplifier goes next to the shunt, not next to the controller. Amplify
  first, then route.
* No switching current is allowed to share copper with the sense return.

### 1.5 Grounding

One ground. There is no split, no star point and no moat.

* L2 is a solid plane and stays solid.
* Separation between quiet and noisy return current is achieved by *placement*,
  so that the noisy return currents have no reason to flow under the quiet
  parts. Cutting the plane to force it achieves the opposite: it makes the
  return current take a longer path, which increases the loop area of exactly
  the loop that was supposed to be quietened.
* The analogue section around the LDO is placed at the far end of the board
  from the switching stages, and its return current path to the connector does
  not cross any switching stage.

---

## 2. Thermal

The board is the heatsink. There is no other one, and there is no airflow.

* Every exposed pad gets a via array: 0.3 mm drill, 1.0 mm pitch, through to L4
  and to the L3 plane it belongs to. That is 9 vias minimum under the buck
  FETs.
* L4 copper under the FETs and the inductor is poured solid and is not
  interrupted by routing. The thermal model in `docs/thermal_model.md` assumes
  a coupled area of 60 percent of the board; carving L4 up with tracks is how
  that assumption stops being true.
* The two buck FETs sit apart rather than side by side, so their heat spreads
  into different copper.
* The LDO dissipates 0.68 W, which is more than either boost FET. It is a
  thermal component, not a small signal one, and it gets the same via
  treatment.

---

## 3. Placement order

1. Connectors, fixed by the mechanical requirement.
2. Input filter chain in physical order from the connector: fuse, diode,
   differential mode inductor, film capacitor, bulk capacitor, ceramics. The
   emissions model assumes the filter is a chain and not a star.
3. +5V power stage: FETs, ceramics, inductor, shunt, sense amplifier.
4. +5V controller and its compensation, close to the FETs.
5. +3V3 stage, fed from the +5V output capacitor bank.
6. +12V boost stage.
7. Analogue corner: LDO, its input filter resistor, its capacitors, the
   preload, at the far end from the switchers.

---

## 4. What a review should check

A layout is not finished until somebody has answered these with a measurement
off the CAD file, not an opinion.

- [ ] Input loop area, per stage, in mm squared.
- [ ] Switch node copper area, per stage, in mm squared.
- [ ] Any track on any layer within 1 mm of a switch node.
- [ ] Any break in L2 under any switching loop.
- [ ] Via count under each exposed pad.
- [ ] Length of the FB track from divider to controller pin.
- [ ] Whether the current sense pair shares copper with power current anywhere.
- [ ] Continuous copper width and length on every path carrying more than 1 A,
      against a current density target of 2 A per mm of width at 2 oz.

---

## 5. The honest caveat

The conducted emissions pre-scan in this repository is differential mode only.
Common mode emissions are driven by the switch node's dv/dt into parasitic
capacitance to chassis and earth, and that capacitance is a property of the
layout. There is no layout, so there is no common mode prediction, and on real
hardware common mode is very often the term that actually fails. A pass in
`test-results/emc-prescan/` means the differential mode filter is sized
sensibly. It does not mean the board will pass.
