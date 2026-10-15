# +5V buck: peak current mode, Type II compensation

The working, by hand, for the loop that
`test-results/bode/5v_loop_gain.png` plots. Every number here is recomputed by
`simulation/smps/design.py` and checked against the switching simulation in
`tests/test_validation.py`.

Target: crossover 50 kHz, phase margin at least 55 degrees, gain margin at
least 8 dB, across 8 to 36 V input and 0.5 to 5 A load.

---

## 1. The plant

Power stage, from `components.BUCK5`:

```
L        = 6.8 uH            DCR      = 11 mOhm
Cout     = 46.2 uF           ESR      = 0.67 mOhm   (three 22 uF in parallel)
Rds(on)  = 11 mOhm both devices
fsw      = 500 kHz           Ts       = 2 us
Ri       = 5 mOhm shunt x 10 amplifier = 0.05 V/A
```

At the design point, 24 V in and 5 A out, the duty ratio including conduction
drops is **D = 0.2129**, so **D' = 0.7871**.

### Slope compensation

```
Sn = Ri (Vin - Vout) / L = 0.05 * 19 / 6.8e-6 = 139.7 kV/s
Sf = Ri  Vout        / L = 0.05 *  5 / 6.8e-6 =  36.8 kV/s
```

Set `Se = Sf`. Then

```
mc = 1 + Se/Sn = 1.263
mc D' = 0.994                      (exactly 1 for the lossless duty ratio)
Qp = 1 / (pi (mc D' - 0.5)) = 0.644
Fm = 1 / ((Sn + Se) Ts) = 1 / (176.5e3 * 2e-6) = 2.833 V^-1
```

`docs/design_notes.md` section 4 has the argument for why `Se = Sf` in
particular. The short version is that it makes `mc D' = 1` at every duty ratio,
so the damping of the pole pair at `fsw/2` does not drift across the input
range, and it makes the whole loop gain independent of input voltage.

### Control to output

Closing the current comparator loop around the averaged power stage:

```
Gvc(s) = Gvd(s) Fm / (1 + Fm Ri He(s) Gid(s))
```

Evaluated numerically, at the design point:

```
|Gvc(0)|      = 15.38     (23.7 dB)
dominant pole = 4.48 kHz
ESR zero      = 1/(2 pi * 0.67e-3 * 46.2e-6) = 5.1 MHz     (irrelevant here)
pole pair     = 250 kHz, Q = 0.644
```

The dominant pole is not at `1/(2 pi R C) = 690 Hz`. The current loop has moved
it up by roughly `1 + 2 R Ts / L`, which is what current mode control does to a
buck: it turns the LC double pole into a single real pole plus a pair up at
half the switching frequency. That is the whole reason a Type II compensator is
enough here and a Type III is not needed.

---

## 2. Placing the compensator

Type II around a transconductance error amplifier:

```
Gc(s) = Kdiv * gm * Z(s)          Z = ro || (Rc + 1/sCc) || 1/sCp
```

One zero, one pole above crossover, and an integrator. Placement rules used:

* **Zero on the plant's dominant pole, 4.48 kHz.** That cancels it, so the loop
  gain falls at a clean 20 dB per decade from below the zero all the way
  through crossover. The alternative, putting the zero at `fc/5`, gives a
  little more phase at crossover but leaves a 40 dB per decade stretch below it
  where the loop is less predictable across load.
* **Pole at fsw/2, 250 kHz.** Far enough above 50 kHz to cost little phase,
  low enough to attenuate switching frequency ripple appearing on the FB pin.
* **Gain solved for**, not guessed: `Rc` is found numerically so that
  `|Gc(fc) Gvc(fc)| = 1` at exactly 50 kHz, then snapped to E24 and E12 values
  and the achieved crossover reported.

### Divider

```
Vref = 0.8 V,  Rbot = 4.99 kOhm (E96)
Rtop = 4.99k * (5.0 - 0.8) / 0.8 = 26.2 kOhm -> 26.1 kOhm (E96)
Kdiv = 4.99 / (26.1 + 4.99) = 0.16050
Vout = 0.8 / 0.16050 = 4.9844 V      (-0.31 % from nominal)
```

### The gain calculation

At 50 kHz the plant is well above its dominant pole, so

```
|Gvc(50 kHz)| ~ 15.38 * 4.48/50 * (pole pair correction) = 1.33
```

and with `gm = 1.2 mS` the mid-band compensator impedance needed is

```
|Z| = 1 / (Kdiv * gm * |Gvc|) = 1 / (0.1605 * 1.2e-3 * 1.33) = 3.90 kOhm
```

Between its zero and its pole a Type II network is resistive, so `Z ~ Rc`:

```
Rc = 3.9 kOhm        (E24, and the exact answer to three figures)
Cc = 1 / (2 pi * 4.48e3 * 3.9e3) = 9.1 nF  -> 10 nF (E12)
Cp = 1 / (2 pi * 250e3 * 3.9e3)  = 163 pF  -> 150 pF (E12)
```

With the snapped values the network's actual corners are

```
fz = 1 / (2 pi * 3.9e3 * 10e-9)  = 4.08 kHz
fp = 1 / (2 pi * 3.9e3 * 150e-12 * 10/(10+0.15)) = 276 kHz
```

---

## 3. Predicted margins

Adding the phase contributions at 50 kHz:

| term | phase at 50 kHz |
|---|---|
| compensator integrator | -90.0 deg |
| compensator zero, 4.08 kHz | +85.3 deg |
| compensator pole, 276 kHz | -10.3 deg |
| plant dominant pole, 4.48 kHz | -84.9 deg |
| plant pole pair, 250 kHz, Q 0.644 | -17.9 deg |
| plant ESR zero, 5.1 MHz | +0.6 deg |
| **total** | **-117.2 deg** |

Phase margin 62.8 degrees by hand. The numeric model gives **62.9 degrees at
49.6 kHz**, and the switching simulation gives **64.7 degrees at 49.9 kHz**.
Gain margin from the model is 12.9 dB, with the -180 degree crossing at
165 kHz.

All three exceed the 55 degree and 8 dB targets with room to spare. The extra
margin is deliberate: nothing in these models includes gate driver delay, dead
time or layout inductance, and all three cost phase on real hardware.

---

## 4. Across the operating range

From `smps.design.all_loops()`:

| operating point | fc | PM | GM |
|---|---|---|---|
| 24 V, 5.0 A | 49.6 kHz | 62.9 deg | 12.9 dB |
| 8 V, 5.0 A | 49.6 kHz | 62.9 deg | 12.9 dB |
| 36 V, 5.0 A | 49.6 kHz | 62.9 deg | 12.9 dB |
| 24 V, 0.5 A | 49.8 kHz | 59.2 deg | 12.7 dB |
| 36 V, 0.5 A | 49.8 kHz | 59.2 deg | 12.7 dB |

The three full load rows being identical to four figures is not a copy and
paste error and it is not a bug. With `Se = Sf` the averaged current mode loop
gain genuinely does not contain `Vin`; section 4 of `docs/design_notes.md`
shows the cancellation. The test suite asserts it to one part in a million,
precisely so that a reader who suspects a bug can see it was checked.

What moves the loop is load, not line, and even that only by a few degrees: at
light load the plant's dominant pole walks down and its DC gain up, which are
close to offsetting.

---

## 5. What would change this

In order of how much:

1. **The error amplifier's transconductance.** `gm = 1.2 mS` is an assumption
   about a controller that has not been selected. Crossover is directly
   proportional to it, so a part with 0.6 mS halves the bandwidth and one with
   2 mS nearly doubles it. `Rc` scales inversely and the fix is one resistor,
   but the number has to come from a datasheet first. It is on
   `outputs/VERIFY.csv`.
2. **Ceramic DC bias derating.** The 46.2 uF assumes a 0.70 retention factor at
   5 V. If the real parts hold 0.55, the plant's dominant pole moves up by a
   third and crossover with it.
3. **Whether the controller lets you set the slope compensation.** Several
   otherwise suitable parts fix `Se` internally, which would break the `mc D' =
   1` result and reintroduce the input voltage dependence.
