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

Type II around a transconductance amplifier, `gm = 0.6 mS`.

```
Vref = 0.8 V,  Rbot = 4.99 kOhm
Rtop = 4.99k * (12 - 0.8) / 0.8 = 69.9 kOhm -> 69.8 kOhm (E96)
Kdiv = 4.99 / (69.8 + 4.99) = 0.066720
Vout = 0.8 / 0.066720 = 11.990 V        (-0.08 % from nominal)
```

Placement:

* **Zero on the plant's dominant pole, 563 Hz**, so the loop falls at a clean
  20 dB per decade through crossover.
* **Pole at fsw/2, 200 kHz.** It is 33 times above crossover and costs
  1.7 degrees, so its only job is ripple rejection at the FB pin.
* **Gain solved for** to put crossover at 6 kHz.

```
Rc = 8.2 kOhm (E24)
Cc = 1 / (2 pi * 563 * 8.2e3) = 34.4 nF -> 33 nF (E12)
Cp = 1 / (2 pi * 200e3 * 8.2e3) = 97 pF -> 100 pF (E12)

achieved:  fz = 588 Hz,  fp = 195 kHz
```

---

## 4. Predicted margins

At 6 kHz:

| term | phase at 6 kHz |
|---|---|
| compensator integrator | -90.0 deg |
| compensator zero, 588 Hz | +84.4 deg |
| compensator pole, 195 kHz | -1.8 deg |
| plant dominant pole, 563 Hz | -84.6 deg |
| **right half plane zero, 37.7 kHz** | **-9.0 deg** |
| plant pole pair, 200 kHz, Q 0.659 | -2.6 deg |
| **total** | **-103.7 deg** |

Phase margin 76.3 degrees, against the numeric model's **76.3 degrees at
5.82 kHz** and the switching simulation's **78.0 degrees at 6.16 kHz**. Gain
margin 14.5 dB with the -180 degree crossing at 49.4 kHz, which the switching
measurement also sees, at 15.7 dB.

The right half plane zero costs only 9 degrees at crossover, which is the
point of putting crossover at `f_rhpz/6.3`. Move crossover to 15 kHz and the
same zero costs 21.7 degrees; move it to 37.7 kHz and it costs 45 degrees while
also flattening the magnitude, and the loop would not close cleanly at all.

The very comfortable 76 degrees is not free bandwidth going spare. It is what a
single pole loop crossing well below every other feature looks like, and the
alternative, pushing crossover up to spend the margin, walks straight into the
zero. The transient performance that costs is visible in
`test-results/transient/12v_load_step.png`: 199 mV of undershoot on a 0.2 A
step and 226 us to settle, against limits of 300 mV and 1 ms. Those limits were
set knowing this rail would be slow.

---

## 5. Across the operating range

| operating point | fc | PM | GM |
|---|---|---|---|
| 5.00 V, 0.40 A | 5.82 kHz | 76.3 deg | 14.5 dB |
| 4.95 V, 0.40 A | 5.76 kHz | 76.2 deg | 14.4 dB |
| 5.05 V, 0.40 A | 5.88 kHz | 76.4 deg | 14.5 dB |
| 5.00 V, 0.10 A | 5.91 kHz | 80.0 deg | 23.0 dB |

Light load improves everything, because the right half plane zero moves up with
`1/R` while the crossover barely moves.

---

## 6. What would change this

1. **A controller that fixes its own slope compensation internally.** At
   `D = 0.58` the value of `Se` is not a refinement, and a part that sets it for
   a different duty range would need the inductor or the switching frequency
   reconsidered.
2. **The minimum on time and the maximum duty clamp.** At 400 kHz the off time
   is 1.04 us and there is plenty of room, but a controller with a long leading
   edge blanking window would eat into the sensed current waveform.
3. **Ceramic derating at 12 V**, taken as 0.55. It sets the dominant pole and
   therefore where the compensator zero belongs.
