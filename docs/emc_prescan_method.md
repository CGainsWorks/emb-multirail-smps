# Conducted emissions pre-scan: method and limits

What `simulation/smps/emc.py` computes, what the result means and, more
importantly, what it does not mean.

---

## 1. What is modelled

The input current of a buck converter is a pulse train. It steps up to the
inductor current when the high side device turns on, ramps with the inductor,
and drops to zero when it turns off. Its harmonics run out well past 30 MHz.
The job of the input filter is to shunt those harmonics back into the loop that
made them so that what reaches the supply lead stays under a limit line.

The model is:

1. **Source.** The pulse train as a trapezoid, with the real rise and fall
   times, decomposed into harmonics up to 40 MHz. Using a trapezoid rather than
   a rectangle matters: a rectangle's envelope falls at 20 dB per decade for
   ever, while the real edge puts a second corner at `1 / (pi t_rise)` and
   everything above that falls at 40 dB per decade. For 12 ns edges that corner
   is at 26 MHz, and below it the two agree.

2. **Filter.** A current divider through the local ceramic and bulk capacitor
   bank, then through the differential mode inductor into the film capacitor
   and the LISN. Every capacitor carries ESR and ESL, because above a few MHz
   a capacitor is an inductor and modelling it as a capacitance produces a
   prediction that is wrong in the optimistic direction.

3. **LISN.** 50 ohms in series with 5 uH, which is what a CISPR artificial
   network presents. The result is the voltage across the 50 ohms, in dB
   microvolts.

Run by `run_all.py`, output in `test-results/emc-prescan/`.

---

## 2. The limit line, and why it is in quotation marks

The line drawn on the plot is EN 55032 Class B quasi peak for conducted
emissions:

```
150 kHz to 500 kHz   66 dBuV falling linearly with log f to 56 dBuV
500 kHz to 5 MHz     56 dBuV
5 MHz to 30 MHz      60 dBuV
```

**The DC input of this board is not a mains port**, so that limit does not
formally apply to it. It is used here as a reference envelope for two reasons:
it is the strictest commonly quoted conducted line, so passing it is a
meaningful statement; and a pre-scan needs something to compare against or it
is just a spectrum.

The real limit has to come from whatever the end product is certified to. For a
24 V industrial DC input that might be EN 55011, for a vehicle installation
CISPR 25 with its banded limits and different measurement setup. Choosing the
right one is a compliance question, not a design one, and it has not been
answered here.

---

## 3. Result

From `test-results/emc-prescan/summary.csv`:

| Vin | worst margin | at |
|---|---|---|
| 8 V | +4.7 dB | 500 kHz |
| 24 V | +8.0 dB | 500 kHz |
| 36 V | +11.2 dB | 500 kHz |

The worst case is the fundamental at the switching frequency at low line, where
the duty ratio is largest and the input pulse widest. **4.7 dB is thin.** For a
prediction with this much assumed in it that is not a comfortable margin, and
it is the first thing a real pre-scan should look at.

The switching frequency sitting exactly on the 500 kHz band edge, where the
limit steps down from a falling line to a flat 56 dBuV, is not a coincidence
worth being pleased about. It is the worst place to put a fundamental. Moving
the +5V stage to 450 kHz would put it in the sloped part of the band where the
limit is 57.1 dBuV and, more usefully, move the second harmonic away from where
the third harmonic of a 300 kHz stage would sit if one were ever added. That is
a change worth considering once there is a measurement to justify it against.

---

## 4. The input filter is also a stability problem

A converter running closed loop draws constant power. Below its loop bandwidth
that makes it a **negative** incremental resistance of magnitude `Vin^2 / Pin`.
Put a lightly damped LC filter in front of a negative resistance and the pair
oscillates, whatever the control loop's phase margin says.

Middlebrook's criterion asks that the filter's output impedance stays well
below the converter's input impedance at every frequency. From
`test-results/emc-prescan/summary.csv`:

| Vin | filter Zout peak | converter Zin | separation |
|---|---|---|---|
| 8 V | 0.50 ohm at 3.15 kHz | 2.68 ohm | 14.6 dB |
| 24 V | 0.50 ohm at 3.15 kHz | 23.6 ohm | 33.5 dB |
| 36 V | 0.50 ohm at 3.15 kHz | 52.3 ohm | 40.4 dB |

Low line is the binding case, because that is where the input current, and
therefore the negative conductance, is largest.

The peak of the filter output impedance is roughly `Q sqrt(L/C)`, so the bulk
capacitance is what keeps it low before any damping is applied. That is why the
bulk capacitor is 220 uF and not the 47 uF the ripple requirement alone would
ask for: at 47 uF the peak rises to 1.9 ohm and the separation falls to 3.2 dB,
which fails. `tests/test_losses_thermal_emc.py` asserts both, so that nobody
shrinks the part to save board area without the test noticing. The aluminium
polymer part's ESR then supplies part of the damping, with the input inductor's
own resistance and the supply lead supplying the rest.

This is the trade-off the whole input filter design turns on:

| L_dm | emissions margin at 8 V | Middlebrook separation |
|---|---|---|
| 2.2 uH | -0.2 dB, fails | best |
| 4.7 uH | +6.5 dB | good |
| **10 uH** | **+4.7 dB with 220 uF bulk** | **14.6 dB** |
| 22 uH | better | worse |

More inductance helps emissions and hurts stability. The chosen point is 10 uH
with 220 uF, and the test suite asserts the direction of both effects so the
choice reads as a choice.

---

## 5. What this is not

**It is not a measurement.** There is no chamber, no LISN, no spectrum analyser
and no board.

**It is differential mode only.** Common mode emissions are driven by the
switch node's dv/dt into parasitic capacitance to chassis and earth. That
capacitance is a property of the layout, and there is no layout. On real
hardware common mode is very often the term that actually fails.

**It has no detector model.** The limit line quoted is quasi peak; the model
computes harmonic amplitudes, which for a repetitive signal like this are close
to what a quasi peak detector reports but are not the same thing.

**It ignores the other two switchers.** The +3V3 and +12V stages both draw
pulsed current from the +5V rail, and some of that reaches the input through
the +5V stage's own control loop and its input impedance. Modelling that
properly means cascading the converters' input and output impedances, which is
a larger job than this pre-scan, and it is on the open items list.

A pass here means the differential mode filter is sized sensibly. It does not
mean the board will pass.

---

## 6. What a real pre-scan would need

1. LISN, spectrum analyser with a quasi peak detector, and the board on a
   ground reference plane at the specified height.
2. Full load on every rail, at 8, 24 and 36 V.
3. Separate common mode and differential mode measurements, using either a
   mode separator or the two line voltages summed and differenced.
4. Near field probe sweep over the board to find which loop the peaks come
   from, which is the measurement that actually tells you what to change.

The reason the differential mode prediction was worth doing anyway is that it
sizes the filter before the board is laid out, and the filter's physical
position in the placement order is a layout constraint that is expensive to fix
afterwards.
