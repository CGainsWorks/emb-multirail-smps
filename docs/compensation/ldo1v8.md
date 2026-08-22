# +1V8A LDO: what is designed here and what is inherited

The other three rails have loops this project designs. This one does not. The
LDO's compensation is inside a bought in part, and no part has been selected.
What this design controls is the output capacitor, the preload, the input
filter and the thermal budget, so those are what this file is about.

Being clear about the difference matters, because a Bode plot of an LDO loop
drawn from a behavioural model looks exactly like a Bode plot of a loop
somebody designed, and it is not one.

---

## 1. The job

```
Vin    +3V3 rail, 3.3 V nominal, 1 % band
Vout   1.8 V, 0.5 A
ripple 2 mVpp maximum
noise  low enough for an ADC reference and analogue front end
```

The rail exists because the +3V3 buck switches at 1 MHz and an analogue
front end does not want 1 MHz on its supply. Efficiency is not the point: at
1.8 V from 3.3 V the best a linear regulator can do is 55 percent, and 0.68 W
of the board's 3 W total loss is this device turning volts into heat on purpose.

---

## 2. The behavioural model, and its status

`smps.design.ldo_loop_gain` builds a loop gain from:

```
a0            = 60 dB
internal pole = 200 Hz
output pole   = 1 / (2 pi r_out(Iload) Cout)
comp zero     = half the output pole, tracking it
parasitic pole= 400 kHz
r_out(I)      = 1 / (gm A_local),  gm = 2 I / Vov,  Vov = 0.35 V, A_local = 20
```

**Every one of those numbers is an assumption.** None is from a datasheet, none
is measured, and the file says so in its docstring and in `STATUS.md`. The
compensation zero tracking the output pole is not a guess about one part: it is
the mechanism any device advertised as stable with any ceramic output capacitor
has to use, because otherwise the output pole walking down at light load runs
straight into the second pole and the loop peaks.

What the model is good for is answering the question this design does control:
does the chosen output capacitor and preload keep the loop stable across the
whole load range. It says yes:

| load | crossover | phase margin |
|---|---|---|
| 0.50 A | 186 kHz | 74.1 deg |
| 50 mA | 294 kHz | 69.0 deg |
| no external load, preload only | 314 kHz | 56.6 deg |

What the model is not good for is predicting the real part's bandwidth, and
nothing downstream depends on that number.

---

## 3. The preload, and why it is fitted

Without a minimum load the output pole walks down towards DC as the pass
device's transconductance falls with its own current, and the loop runs out of
places to put its zero. A 180 ohm resistor holds 10 mA:

```
I_preload = 1.8 / 180 = 10 mA
P_preload = 1.8 * 10e-3 = 18 mW
```

18 mW to stop a rail ringing on an unloaded board is a good trade, and the
alternative is discovering it at bring-up. Whether the eventually chosen part
actually needs it is on `outputs/VERIFY.csv`; if it does not, the resistor
becomes a do-not-fit and costs nothing.

---

## 4. The input filter, which is a real finding

The LDO's own supply rejection is not enough.

The +3V3 buck's specified ripple limit is 20 mVpp at 1 MHz. The modelled LDO
PSRR at 1 MHz is **7.8 dB**, because by then the loop gain has long since run
out and all that is left is the divider formed by the pass device's output
impedance and the output capacitor. That gives

```
20 mVpp * 10^(-7.8/20) = 8.1 mVpp
```

against a 2 mVpp budget. It fails by a factor of four.

The simulated 3V3 ripple is only about 3.6 mVpp, so on the simulated numbers it
would scrape through at 1.5 mVpp. Designing to the simulated value rather than
the specified limit would be designing to the model instead of the
requirement, so the filter was added:

```
Rf1 = 0.33 Ohm in series into the existing 10 uF input capacitor
pole = 1 / (2 pi * 0.33 * 7e-6) = 68.9 kHz
attenuation at 1 MHz = 23.3 dB
total rejection = 23.3 + 7.8 = 31.1 dB
20 mVpp -> 0.56 mVpp        inside the 2 mVpp budget
```

Costs:

```
drop     = 0.33 * 0.51 A = 168 mV of headroom
loss     = 0.33 * 0.51^2 = 86 mW
headroom = 3.267 V (3V3 low) - 0.168 - 1.8 = 1.30 V against 0.25 V of dropout
```

An LC would cost far less power for the same attenuation. It was not used
because an undamped LC feeding an LDO is a peaking filter, not a filter: with
`L = 1 uH` and `C = 7 uF` into a 6.5 ohm load the Q is above 30 and the network
would amplify anything near 60 kHz by more than 20 dB. Damping it properly
costs most of the power the LC was supposed to save.

`tests/test_design.py` asserts both that the total rejection meets the budget
and that the filter contributes at least 15 dB of it, so that nobody removes
the resistor to recover the headroom without the test noticing.

---

## 5. What this rail still needs

* A real part number, and its datasheet stability envelope over output
  capacitance and load. Everything in section 2 is a placeholder until then.
* A measured output noise figure. The specification asks for a quiet rail and
  this repository has no basis for claiming one.
* A measured PSRR curve at 1 MHz. It is the number the input filter was sized
  against, and it came out of a model.
