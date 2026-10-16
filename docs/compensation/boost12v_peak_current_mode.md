# +12V boost: peak current mode, Type II compensation

Target: crossover 6 kHz, phase margin at least 50 degrees, gain margin at least
8 dB, from the regulated 5 V rail.

The bandwidth target on this rail is set by physics rather than by preference.
Everything below follows from where the right half plane zero is.

---

## 1. The right half plane zero comes first

Turning the low side device on for longer stores more energy in the inductor,
which is what eventually raises the output. But while it is on, the inductor is
disconnected from the output, so the immediate effect of asking for more is
less. The output moves the wrong way first. That is a zero in the right half
plane: it removes phase like a pole while adding gain like a zero, which is the
worst combination available.

```
f_rhpz = D'^2 R / (2 pi L)
```

At full load, `D = 0.5833`, `D' = 0.4167`, `R = 12/0.4 = 30 Ohm`, `L = 22 uH`:

```
f_rhpz = 0.1736 * 30 / (2 pi * 22e-6) = 37.7 kHz
```

No amount of compensation moves it. Crossover has to sit far enough below it
that the phase it removes has not arrived yet, and a factor of five to six is
the usual rule. **6 kHz** gives 6.3.

The zero moves *up* as the load falls, to 151 kHz at 0.1 A, so full load is the
binding case. It moves *down* if the inductance goes up, which is why this rail
runs 35 percent ripple current rather than the usual 30: a bigger inductor
would be quieter and slower, and slower is not affordable here.
`tests/test_design.py` asserts both the full load ratio and the direction of
the load dependence.

---

## 2. The plant

```
L        = 22 uH             DCR      = 45 mOhm
Cout     = 24.2 uF           ESR      = 1.5 mOhm  (two 22 uF 25 V, derated 0.55)
Rds(on)  = 40 mOhm both devices
fsw      = 400 kHz           Ts       = 2.5 us
Ri       = 50 mOhm shunt x 3 amplifier = 0.15 V/A
```

Slope compensation, same choice as the +5V rail:

```
Sn = Ri Vin / L          = 0.15 * 5 / 22e-6 =  34.1 kV/s
Sf = Ri (Vout - Vin) / L = 0.15 * 7 / 22e-6 =  47.7 kV/s
Se = Sf
mc = 1 + Se/Sn = 2.400
mc D' = 0.983
Qp = 1 / (pi (mc D' - 0.5)) = 0.659
Fm = 1 / ((Sn + Se) Ts) = 4.889 V^-1
```

Note that `Se = Sf` is a stronger requirement on a boost than on a buck. At
`D = 0.583` the converter is past the half duty point where a peak current
loop goes subharmonically unstable without slope compensation, so this is not
an optimisation, it is the thing that makes the loop work at all. With
`Se = 0.5 Sf` the same converter would give `mc D' - 0.5 = 0.21` and a Q of
1.53, which is a visible peak at 200 kHz rather than a flat response.

With the inner loop closed, at the design point:

```
|Gvc(0)|      = 31.2      (29.9 dB)
dominant pole = 563 Hz
right half plane zero = 37.7 kHz
pole pair     = 200 kHz, Q = 0.659
```

---

## 3. The compensator

Type II around a transconductance amplifier. The selected controller is the
TPS43061, and its data sheet gives `VREF = 1.22 V`, `Gea = 1.1 mS` and an
output resistance of 10 MOhm, all typical.

```
Vref = 1.22 V,  Rbot = 4.99 kOhm
Rtop = 4.99k * (12 - 1.22) / 1.22 = 44.1 kOhm -> 44.2 kOhm (E96)
Kdiv = 4.99 / (44.2 + 4.99) = 0.10144
Vout = 1.22 / 0.10144 = 12.026 V        (+0.22 % from nominal)
```

Placement:

* **Zero on the plant's dominant pole, 563 Hz**, so the loop falls at a clean
  20 dB per decade through crossover.
* **Pole at fsw/2, 200 kHz.** It is 33 times above crossover and costs
  1.7 degrees, so its only job is ripple rejection at the FB pin.
* **Gain solved for** to put crossover at 6 kHz.

```
Rc = 3.0 kOhm (E24)
Cc = 1 / (2 pi * 563 * 3.0e3) = 94 nF -> 100 nF (E12)
Cp = 1 / (2 pi * 200e3 * 3.0e3) = 265 pF -> 270 pF (E12)

achieved:  fz = 531 Hz,  fp = 197 kHz
```

Before a controller was chosen this rail assumed a 0.8 V reference and
0.6 mS, which gave 69.8 kOhm, 8.2 kOhm, 33 nF and 100 pF. The higher
reference raises the divider gain by half and the higher transconductance
nearly doubles the amplifier gain, so `Rc` came down to keep the same
crossover.

---

## 4. Predicted margins

At 6 kHz:

| term | phase at 6 kHz |
|---|---|
| compensator integrator | -90.0 deg |
| compensator zero, 531 Hz | +84.9 deg |
| compensator pole, 197 kHz | -1.7 deg |
| plant dominant pole, 563 Hz | -84.6 deg |
| **right half plane zero, 37.7 kHz** | **-9.0 deg** |
| plant pole pair, 200 kHz, Q 0.659 | -2.6 deg |
| **total** | **-103.0 deg** |

Phase margin 77.0 degrees, against the numeric model's **76.6 degrees at
5.94 kHz** and the switching simulation's **78.3 degrees at 6.26 kHz**. Gain
margin 14.3 dB with the -180 degree crossing at 49.6 kHz, which the switching
measurement also sees, at 15.5 dB.

The right half plane zero costs only 9 degrees at crossover, which is the
point of putting crossover at `f_rhpz/6.3`. Move crossover to 15 kHz and the
same zero costs 21.7 degrees; move it to 37.7 kHz and it costs 45 degrees while
also flattening the magnitude, and the loop would not close cleanly at all.

The very comfortable 76 degrees is not free bandwidth going spare. It is what a
single pole loop crossing well below every other feature looks like, and the
alternative, pushing crossover up to spend the margin, walks straight into the
zero. The transient performance that costs is visible in
`test-results/transient/12v_load_step.png`: 198 mV of undershoot on a 0.2 A
step and 241 us to settle, against limits of 300 mV and 1 ms. Those limits were
set knowing this rail would be slow.

---

## 5. Across the operating range

| operating point | fc | PM | GM |
|---|---|---|---|
| 5.00 V, 0.40 A | 5.94 kHz | 76.6 deg | 14.3 dB |
| 4.95 V, 0.40 A | 5.87 kHz | 76.5 deg | 14.2 dB |
| 5.05 V, 0.40 A | 6.00 kHz | 76.7 deg | 14.4 dB |
| 5.00 V, 0.10 A | 6.02 kHz | 80.5 deg | 22.9 dB |

Light load improves everything, because the right half plane zero moves up with
`1/R` while the crossover barely moves.

---

## 6. What would change this

1. **The controller's own slope compensation.** The TPS43061 sets it
   internally. At `D = 0.58` the value of `Se` is not a refinement; if the
   data sheet's internal ramp differs from what this model assumes, the
   inductor or the switching frequency has to be reconsidered. The current
   sense gain, modelled as x3 on the 50 mOhm shunt, has the same status.
2. **The minimum on time and the maximum duty clamp.** At 400 kHz the off time
   is 1.04 us and there is plenty of room, but a controller with a long leading
   edge blanking window would eat into the sensed current waveform.
3. **Ceramic derating at 12 V**, taken as 0.55. It sets the dominant pole and
   therefore where the compensator zero belongs.
