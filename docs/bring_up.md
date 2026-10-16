# Bring-up procedure

**Not performed.** No board exists. This is the procedure written before the
board, with the expected values taken from the simulations, so that when a
board does exist the comparison is against a prediction made in advance rather
than one adjusted afterwards.

Every expected value below is a link back to a number this repository computes.
If a measurement disagrees, that is a result worth recording, not a number to
quietly update.

---

## Equipment

* Bench supply, 40 V 3 A, with current limit.
* Oscilloscope, 200 MHz or better, with a short ground spring. Not a ground
  clip lead. Half of switch node measurement is the probe.
* Electronic load, at least 5 A, constant current mode with a fast transient
  step.
* Multimeter, four and a half digits, for regulation.
* Frequency response analyser or a scope with a Bode option, for section 6.
* Thermocouples or a thermal camera, for section 8.
* Near field probes, for section 9.

---

## 0. Before power

- [ ] Visual: solder bridges, tombstoned parts, polarity of C3, D1 and the LDO.
- [ ] Continuity: every rail to ground. Expect no short. The +1V8A rail reads
      180 ohms because of the preload, which is a useful confirmation the
      preload is fitted.
- [ ] Resistance of the feedback dividers, in circuit, against
      `outputs/compensation_values.csv`.
- [ ] Confirm the current sense shunt is the four terminal part and the sense
      traces come off the sense terminals.

## 1. Input stage only, no controllers

Fit the input filter chain and nothing else, or hold every controller in
shutdown.

- [ ] Ramp the supply from 0 to 36 V with a 100 mA limit. Expect no current
      beyond leakage.
- [ ] Reverse the supply to -36 V briefly with a 50 mA limit. Expect the series
      diode to block and nothing downstream to see it.
- [ ] Measure the drop across D1 at 1 A. Compare against the loss model's
      assumption.

## 2. +5V rail, no load

- [ ] Vin 24 V, no load. Expect **4.984 V**, from the E96 divider, not 5.000 V.
      `docs/design_notes.md` section 6.
- [ ] Switch node on the scope. Expect 500 kHz, duty about 0.21.
- [ ] Look at the switch node ringing frequency and amplitude. This is the
      first number that tells you whether the layout met
      `docs/layout_rules.md`. There is no prediction for it in this repository
      because it depends entirely on a layout that did not exist when these
      documents were written. Record it.
- [ ] Output ripple, AC coupled, 20 MHz bandwidth limit, ground spring.
      Expect **6.4 mVpp** at full load, against a 25 mVpp specification.

## 3. +5V rail, loaded

- [ ] Step the load 0.25, 1.25, 2.5, 3.75, 5.0 A. Compare against
      `test-results/load-regulation/load_regulation.csv`. Expect deviation
      under 0.01 percent, which is small enough that the meter's resolution is
      the limit, not the converter.
- [ ] Sweep the input 8, 12, 18, 24, 30, 36 V at full load. Compare against
      `test-results/line-regulation/line_regulation.csv`.
- [ ] At full load and 36 V, check the inductor is not saturating: the current
      waveform through the shunt should stay a straight ramp. A knee at the top
      is saturation.

## 4. Downstream rails

Bring up in tree order and confirm each before enabling the next.

- [ ] +3V3, expect **3.321 V**. Ripple at full load, expect about 2.7 mVpp.
- [ ] +12V, expect **12.026 V**. Ripple at full load, expect about 25.7 mVpp.
- [ ] +1V8A, expect 1.800 V. Ripple, expect well under 1 mVpp.
- [ ] With every rail at full load, confirm the +5V stage is delivering about
      **4.6 A**, not the 1.5 A its connector is rated for. That is the power
      tree working as `smps.losses.solve_power_tree` says it does.

## 5. Load transients

Electronic load in fast transient mode, scope AC coupled on the output.

| rail | step | expected undershoot | expected settling |
|---|---|---|---|
| +5V | 1.5 A | 99 mV | 28 us |
| +3V3 | 1.0 A | 43 mV | 5 us |
| +12V | 0.2 A | 198 mV | 241 us |

Limits are 150 mV / 100 us, 100 mV / 50 us and 300 mV / 1 ms respectively.

## 6. Loop gain

This is the measurement the whole project is built around, so it is worth doing
carefully.

- [ ] Replace the 0 ohm injection link with 20 ohm: R14 on +5V, R22 on +3V3,
      R32 on +12V. Each sits between the rail and the top of its divider.
- [ ] Inject across it with the analyser's isolation transformer. Measure
      channel A on the output side, channel B on the divider side. Loop gain is
      `-A/B`, which is the same formula
      `simulation/smps/loopmeas.py` uses.
- [ ] Keep the injection small. Sweep once at the chosen amplitude and once at
      double, and confirm the answer does not move. That is the same linearity
      check the simulation runs, and it is the difference between measuring a
      loop gain and measuring a large signal behaviour.
- [ ] Compare against `test-results/bode/*_loop_gain.png`:

| rail | expected fc | expected PM |
|---|---|---|
| +5V | 50.5 kHz | 60.9 deg |
| +3V3 | 100.2 kHz | 63.3 deg |
| +12V | 5.9 kHz | 76.6 deg |

Expect the measured phase to be **worse** than the prediction, by five to
fifteen degrees at crossover. Neither the analytic model nor the switching
simulation includes gate driver propagation delay, dead time or layout
inductance, and all three cost phase. A measurement that comes in better than
predicted is more suspicious than one that comes in worse.

## 7. Efficiency

- [ ] Four wire measurement on both the input and every output. A two wire
      measurement at these currents puts the lead resistance straight into the
      answer.
- [ ] Sweep load from 10 to 100 percent at 8, 24 and 36 V.
- [ ] Compare against `test-results/efficiency/system_efficiency.csv`, which
      predicts 87.9 percent at 24 V and full load.
- [ ] If the measurement is low, look at the switching loss term first. It is
      the largest and least certain line in the model, and
      `docs/loss_model.md` says why.

## 8. Thermal

- [ ] Full load on every rail, 36 V input, still air, until stable. Allow at
      least 20 minutes.
- [ ] Thermal image with an emissivity reference on each package measured.
- [ ] Compare board temperature against **79.8 C** at 55 C ambient, scaled for
      the actual ambient. Expect the high side buck FET at about 94 C junction
      and the LDO at about 93 C.
- [ ] Expect the FET hot spot to be **worse** than predicted and the parts far
      from the power stages to be better. The model treats the board as
      isothermal and it is not.

## 9. EMC near field pre-scan

- [ ] Near field loop probe over each switching stage, full load, 36 V. Find
      the loudest loop.
- [ ] Compare which loop is loudest against the input loop areas measured off
      the CAD file during layout review. They should agree about which stage is
      worst.
- [ ] Conducted scan with a LISN if one is available, against
      `test-results/emc-prescan/conducted_prescan.png`. Expect the differential
      mode fundamental to be near the prediction and the rest of the spectrum
      to be worse, because common mode is not in the model at all.

---

## Recording

Every measurement in this procedure has a predicted value in this repository.
When they are taken, they belong in `test-results/` alongside the simulated
ones, in files clearly named as measured, with the simulated ones kept rather
than overwritten. The comparison between a prediction made before the board and
a measurement made after it is the only thing that makes either of them
interesting.
