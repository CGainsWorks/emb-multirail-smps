# Design notes

The reasoning behind the topology choices, the power stage sizing worked out by
hand, and the closed forms that `simulation/smps/statespace.py` is checked
against in `tests/test_smallsignal.py`.

Nothing in this file has been measured. Where a number appears it comes from
the specification in `docs/spec.md` and the component values in
`simulation/smps/components.py`, and the code recomputes it. If a number here
and a number in `test-results/` disagree, the code is right and this file is
stale; `make demo` and the test suite are what keep them together.

---

## 1. Why this power tree

```
VIN 8-36 V ── buck ──> +5V ──┬── buck ──> +3V3 ── LDO ──> +1V8A
                             └── boost ─> +12V
```

The alternative was four independent stages all fed from VIN. Cascading was
chosen for three reasons and it costs something for each of them.

**The wide input range only has to be solved once.** A converter that has to
work from 8 V to 36 V spans a 4.5:1 duty ratio range. That constrains the
minimum on time at high line, the slope compensation, and the inductor sizing,
which has to be done for the worst corner rather than the nominal one. Doing
that once, on the stage that carries the most power, is cheaper than doing it
four times. The +3V3 buck sees a regulated 5 V input with a one percent band,
so it can run at 1 MHz with a 1.5 uH inductor and a voltage mode loop that
would be uncomfortable across 8 to 36 V.

**The +12V rail is a boost, so it needs a source below 12 V.** From a 24 V
nominal input a 12 V rail would be a buck, but at the 8 V corner it would have
to be a boost, and a buck-boost that has to cross over mid range is a
noticeably harder thing to compensate than either. Feeding the boost from the
regulated 5 V rail removes the mode change entirely.

**What it costs.** Efficiency multiplies. The +3V3 rail's power passes through
two conversions, so its end to end efficiency is the product, and the +1V8A
rail passes through three of which the last is linear. The whole board comes
out around 88 percent at nominal input rather than the low 90s a set of
independent stages would give. It also concentrates load: the +5V stage carries
4.6 A when only 1.5 A of that reaches a connector, which is why
`smps.losses.solve_power_tree` works the tree backwards in code rather than
leaving it to a hand written budget.

---

## 2. Why each control scheme

| rail | control | why |
|---|---|---|
| +5V | peak current mode | 4.5:1 input range. Current mode makes the plant look first order and, with the right slope compensation, makes the loop gain independent of input voltage (section 4). It also gives cycle by cycle current limiting for free, which on the stage carrying the whole board is worth having. |
| +3V3 | voltage mode | Fixed 5 V input, so the main argument for current mode does not apply. At 1 MHz, sensing 3 A of inductor current accurately enough for a current loop costs a shunt, an amplifier and a blanking window; a sawtooth and a comparator cost none of that. The price is a Type III compensator instead of a Type II, which is six passives instead of three. |
| +12V | peak current mode | The right half plane zero already limits the bandwidth hard, so the extra phase a voltage mode loop would need to claw back from an LC double pole is phase there is no room for. |
| +1V8A | linear | It exists to be quiet, not efficient. |

---

## 3. Power stage sizing

All of this is in `simulation/smps/sizing.py`, which reports required against
chosen for every line and is asserted in `tests/test_design.py`.

### +5V buck

Ripple current is worst at maximum input voltage, because that is where the
duty ratio is smallest and the off time longest:

```
D(36 V)  = 5 / 36                     = 0.1389
L        = Vout (1 - D) / (dI * fsw)
         = 5 * 0.8611 / (1.5 * 500e3) = 5.74 uH   for dI = 30 % of 5 A
```

6.8 uH is the next standard value up, which gives

```
dI(36 V) = 5 * 0.8611 / (6.8e-6 * 500e3) = 1.266 A      (25.3 % of 5 A)
dI(24 V) = 5 * 0.7917 / (6.8e-6 * 500e3) = 1.164 A
dI(8 V)  = 5 * 0.3750 / (6.8e-6 * 500e3) = 0.552 A
Ipeak    = 5 + 1.266/2                    = 5.63 A
```

against a 9 A saturation rating, so 60 percent headroom on the worst corner.

Output capacitance for the 25 mVpp ripple budget, allocating 60 percent of it
to the capacitive term and leaving the rest for ESR and layout:

```
C >= dI / (8 fsw dV) = 1.266 / (8 * 500e3 * 0.015) = 21.1 uF
```

Three 22 uF 25 V X7R parts in 1210 give 66 uF on the label and **46.2 uF** in
the circuit, because an X7R MLCC loses about 30 percent of its capacitance at
5 V of DC bias. Every capacitance in this repository is the derated one. The
derating factors are in `components.CERAMIC_DERATING` and they are assumptions;
ignoring them is the usual reason a bench ripple measurement comes in two or
three times worse than the simulation said.

### +3V3 buck

Fixed 5 V input, so there is no worst corner to hunt for:

```
D  = 3.3 / 5                                   = 0.66
L  = 3.3 * 0.34 / (0.9 * 1e6)                  = 1.25 uH  ->  1.5 uH chosen
dI = 3.3 * 0.34 / (1.5e-6 * 1e6)               = 0.748 A  (24.9 % of 3 A)
C  = 2 x 22 uF 16 V X7R, derated 0.75          = 33 uF
f_LC = 1 / (2 pi sqrt(1.5e-6 * 33e-6))         = 22.6 kHz
```

The LC double pole at 22.6 kHz has to sit well below the 100 kHz crossover for
a Type III compensator to have anywhere to put its zeros. A factor of 4.4 is
comfortable.

### +12V boost

```
D    = 1 - 5/12                                 = 0.5833
IL   = 0.4 / (1 - D)                            = 0.960 A
L    = Vin D / (dI fsw) for dI = 35 % of IL     = 24.8 uH -> 22 uH chosen
dI   = 5 * 0.5833 / (22e-6 * 400e3)             = 0.331 A
Ipk  = 0.960 + 0.166                            = 1.126 A   (2.5 A rating)
```

Thirty five percent ripple rather than the usual thirty, on purpose. The right
half plane zero sits at

```
f_rhpz = D'^2 R / (2 pi L) = 0.4167^2 * 30 / (2 pi * 22e-6) = 37.7 kHz
```

so a *larger* inductor would push the zero *down* and take the achievable loop
bandwidth with it. On a boost, inductor ripple current is the thing worth
spending to keep the zero where it is. Crossover is placed at 6 kHz, a factor
of 6.3 below the zero at full load, and the zero only moves up as the load
falls.

Output capacitance is set by the capacitor supplying the entire load through
the on time, which is a different calculation from a buck:

```
C >= Iout D / (fsw dV) = 0.4 * 0.5833 / (400e3 * 0.030) = 19.4 uF
```

Two 22 uF 25 V parts at 12 V of bias derate to **24.2 uF**.

---

## 4. Peak current mode, and why Se = Sf

The artificial ramp slope `Se` is usually set somewhere between half and one
times the falling inductor current slope `Sf`. Setting it exactly equal has a
property worth having on a rail with a 4.5:1 input range.

The sensed slopes are

```
Sn = Ri (Vin - Vout) / L      rising, during the on time
Sf = Ri Vout / L              falling, during the off time
```

so `Sf / Sn = Vout / (Vin - Vout) = D / D'`. With `Se = Sf`,

```
mc = 1 + Se/Sn = 1 + D/D' = 1/D'
```

and therefore `mc D' = 1` at **every** duty ratio. The damping of the pole pair
that sampling puts at half the switching frequency is

```
Qp = 1 / (pi (mc D' - 0.5)) = 1 / (pi * 0.5) = 2/pi = 0.637
```

which is a well behaved value, and it stays at that value from 8 V to 36 V
instead of drifting. For this board, with `Ri = 5 mOhm * 10 = 0.05 V/A`:

```
Sn(24 V) = 0.05 * 19 / 6.8e-6 = 139.7 kV/s
Sf       = 0.05 *  5 / 6.8e-6 =  36.8 kV/s
mc       = 1.263,  D' = 0.787,  mc D' = 0.994,  Qp = 0.644
```

`mc D'` is 0.994 rather than exactly 1 because the duty ratio used includes the
conduction drops, which pushes D up slightly. That is a real effect and not a
modelling error, and the test that checks this identity allows for it.

There is a second consequence, and it is the reason the simulated line
regulation of the +5V rail looks too good to be true. The modulator gain is

```
Fm = 1 / ((Sn + Se) Ts)   and   Sn + Se = Ri Vin / L
```

so `Fm` goes as `1/Vin`, while both `Gvd` and `Gid` go as `Vin`. In the
averaged model the input voltage cancels exactly and the control to output
transfer function does not depend on it at all. `tests/test_smallsignal.py`
asserts this to one part in a million. The real converter will not be perfectly
flat: dead time, gate driver delay and Rds(on) all move with operating point
and none of them are in the model.

---

## 5. Closed forms, and what the numeric model does instead

`statespace.py` never uses any of the expressions below. It builds two matrices
per converter from Kirchhoff's laws, averages them, and evaluates
`C (sI - A)^-1 B + D` numerically. The closed forms are here so that
`tests/test_smallsignal.py` can check the numeric model against something
derived independently, and so that the tolerances in those tests can be
justified rather than tuned.

**Buck, control to output, ideal:**

```
Gvd(s) = Vin / (1 + s/(w0 Q) + (s/w0)^2)      w0 = 1/sqrt(LC)
Gvd(0) = Vin                                  exactly, no D anywhere
```

Checked to 1e-4 relative. The resonance is checked to 5 percent, because the
magnitude peak of a second order response sits below `w0` by a factor of
`sqrt(1 - 1/(2Q^2))`.

**Boost, control to output, ideal:**

```
Gvd(0)  = Vout / D'
w_rhpz  = D'^2 R / L
w0      = D' / sqrt(LC)
```

The right half plane zero is checked by computing the transmission zeros of the
state space model directly, as the eigenvalues of `A - B D^-1 C`, and asserting
that exactly one of them is in the right half plane and lands within two
percent of `D'^2 R / (2 pi L)`. That is a stronger check than looking at a Bode
plot and agreeing that the phase falls.

The same test asserts that the buck's feedthrough term `D` is zero, which is
the structural reason a buck has no right half plane zero: its inductor feeds
the output node in both switch states, so changing the duty ratio never takes
current away from the load even briefly.

**Current loop closure.** For the two current mode rails the inner loop is
closed as

```
Gvc(s) = Gvd(s) Fm / (1 + Fm Ri He(s) Gid(s))
He(s)  = 1 + s/(wn Qz) + (s/wn)^2      wn = pi/Ts,  Qz = -2/pi
```

rather than by quoting the resulting pole positions. `He(s)` is the second
order approximation to `sTs/(e^{sTs} - 1)`, and it is what puts the pole pair
at half the switching frequency into the response. Leave it out and the model
will cheerfully predict a crossover above `fsw/2` that no converter can
deliver.

---

## 6. Feedback dividers

| rail | Rtop | Rbot | Vref | Vout |
|---|---|---|---|---|
| +5V | 26.1 kOhm | 4.99 kOhm | 0.800 V (LTC3891) | 4.984 V |
| +3V3 | 10.2 kOhm | 3.74 kOhm | 0.891 V (TPS54317) | 3.321 V |
| +12V | 44.2 kOhm | 4.99 kOhm | 1.22 V (TPS43061) | 12.026 V |

The dividers are built from E96 values, so the regulated voltage is not exactly
the nominal one. The errors, -0.31 percent, +0.64 percent and +0.22 percent,
are inside the one to two percent tolerances the specification asks for and
they are systematic, not random, so they are stated rather than hidden. All the
regulation results are quoted against the voltage the divider actually sets.

---

## 7. Things this design does not do

* No input transient suppression beyond a series diode and the 40 V survivable
  rating. If the end application can present a load dump, that is an external
  TVS and it is out of scope.
* No sequencing. The rails come up in tree order because of how they are fed
  and nothing enforces anything stricter.
* No isolation, no telemetry, no digital control.
* Discontinuous conduction is not modelled. All three switchers stay in
  continuous conduction down to about 10 percent load with the ripple currents
  chosen above, and below that the models in this repository stop describing
  the converter. The efficiency curves are plotted down to 2 percent of full
  load anyway, and the light load end of them should be read as optimistic.
